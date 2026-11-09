/* Test driver for core/rh_zip.c: zip_cli <zip> <member> <dest> <max_out>. Prints "rc=<n> <message>". */
#include <stdio.h>
#include <stdlib.h>
#include "../core/rh_zip.h"
int main(int argc, char **argv)
{
	char msg[160]; int rc;
	if (argc != 5) return 99;
	rc = rh_zip_extract(argv[1], argv[2], argv[3], strtoull(argv[4], NULL, 10), msg, sizeof msg);
	printf("rc=%d %s\n", rc, msg);
	return 0;
}
