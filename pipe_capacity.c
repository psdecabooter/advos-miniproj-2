/*
  Part 4a: measure pipe capacity rather than assuming it.

  Folklore says a Linux pipe holds 16 pages.  That is a claim about the
  kernel, and the throughput curve's shape is going to be explained in terms
  of it, so it gets measured on the machine under test.

  Method: make the write end nonblocking, write until write() returns EAGAIN,
  and count the bytes that made it in.  Three numbers are then compared:

    - bytes accepted, one byte per write
    - bytes accepted, larger writes
    - F_GETPIPE_SZ, what the kernel says the capacity is
    - 16 * getconf PAGESIZE, what the folklore says

  The single-byte and bulk figures need not agree.  The kernel accounts for a
  pipe in whole pages but a one-byte write does not necessarily get a page to
  itself, so the byte count can come in under the nominal size.  Which way it
  falls is the interesting part.
*/
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Fill a fresh pipe with writes of chunk bytes; return bytes accepted. */
static long fill(int chunk, int *out_pipe_sz) {
  int fd[2];
  if (pipe(fd) == -1) {
    perror("pipe");
    exit(EXIT_FAILURE);
  }
  if (fcntl(fd[1], F_SETFL, O_NONBLOCK) == -1) {
    perror("F_SETFL");
    exit(EXIT_FAILURE);
  }
  if (out_pipe_sz)
    *out_pipe_sz = fcntl(fd[1], F_GETPIPE_SZ);

  char *buf = calloc(1, chunk);
  if (!buf) {
    perror("calloc");
    exit(EXIT_FAILURE);
  }

  long total = 0;
  for (;;) {
    ssize_t w = write(fd[1], buf, chunk);
    if (w > 0) {
      total += w;
      continue;
    }
    if (w == -1 && (errno == EAGAIN || errno == EWOULDBLOCK))
      break; /* full */
    perror("write");
    exit(EXIT_FAILURE);
  }

  free(buf);
  close(fd[0]);
  close(fd[1]);
  return total;
}

int main(void) {
  long pagesize = sysconf(_SC_PAGESIZE);
  int pipe_sz = 0;

  FILE *csv = fopen("pipe_capacity.csv", "w");
  if (!csv) {
    perror("pipe_capacity.csv");
    return 1;
  }
  fprintf(csv, "method,bytes,pages_at_%ld,note\n", pagesize);

  printf("Pipe capacity, measured\n\n");
  printf("  page size (sysconf):        %ld\n", pagesize);

  long one = fill(1, &pipe_sz);
  printf("  F_GETPIPE_SZ:               %d\n", pipe_sz);
  printf("  16 * page size (folklore):  %ld\n", 16 * pagesize);
  printf("\n  %-28s %12s %10s\n", "fill method", "bytes", "pages");
  printf("  %-28s %12ld %10.2f\n", "single-byte writes", one,
         (double)one / (double)pagesize);

  fprintf(csv, "f_getpipe_sz,%d,%.4f,kernel reported\n", pipe_sz,
          (double)pipe_sz / (double)pagesize);
  fprintf(csv, "folklore_16_pages,%ld,16.0,16 * page size\n", 16 * pagesize);
  fprintf(csv, "single_byte_writes,%ld,%.4f,write() until EAGAIN\n", one,
          (double)one / (double)pagesize);

  /* Bulk writes, to see whether write size changes how much fits. */
  int chunks[] = {16, 64, 256, 1024, 4096};
  for (unsigned i = 0; i < sizeof(chunks) / sizeof(chunks[0]); ++i) {
    long got = fill(chunks[i], NULL);
    char name[64];
    snprintf(name, sizeof(name), "%d-byte writes", chunks[i]);
    printf("  %-28s %12ld %10.2f\n", name, got, (double)got / (double)pagesize);
    fprintf(csv, "chunk_%d,%ld,%.4f,write() until EAGAIN\n", chunks[i], got,
            (double)got / (double)pagesize);
  }

  printf("\n  Verdict: F_GETPIPE_SZ %s 16 * page size.\n",
         pipe_sz == 16 * pagesize ? "matches" : "does NOT match");
  printf("  Single-byte fill reached %.1f%% of the nominal capacity.\n",
         100.0 * (double)one / (double)pipe_sz);

  fclose(csv);
  printf("\nWrote pipe_capacity.csv\n");
  return 0;
}
