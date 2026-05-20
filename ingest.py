import sys

from rag_core import ingest_library, ingest_all, available_libraries


def main(argv):
    if len(argv) == 0:
        print(f"Ingesting all libraries: {available_libraries()}")
        results = ingest_all(reset=True)
        print()
        print("=" * 60)
        print("Summary:")
        for lib, (n, skipped) in results.items():
            print(f"  {lib}: {n} chunks indexed, {skipped} skipped")
        return

    for lib in argv:
        if lib not in available_libraries():
            print(f"Unknown library: {lib}")
            print(f"Available: {available_libraries()}")
            sys.exit(1)

    for lib in argv:
        n, skipped = ingest_library(lib, reset=True)
        print(f"  {lib}: {n} chunks indexed, {skipped} skipped")


if __name__ == "__main__":
    main(sys.argv[1:])
