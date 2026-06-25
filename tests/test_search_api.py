import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ann_search_service import SingleCellANNService


def main() -> None:
    service = SingleCellANNService()
    status = service.status()
    print("Index status:")
    print(status)

    first_cell = service.metadata[0]["cell_id"]
    print(f"\nQuery cell_id: {first_cell}")

    result = service.search(cell_id=first_cell, k=5, nprobe=10)
    print(f"Elapsed: {result['elapsed_ms']} ms")
    print("Top-K results:")
    for rank, item in enumerate(result["results"], start=1):
        print(
            rank,
            item["cell_id"],
            item["cell_type"],
            item["disease"],
            item["distance"],
            item["expression"],
        )


if __name__ == "__main__":
    main()
