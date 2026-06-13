import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dataset_manager import DatasetManager


class LocalUpload:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.filename = path.name

    def save(self, target: str) -> None:
        shutil.copy2(self.path, target)


def print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage single-cell h5ad datasets and FAISS indexes.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List registered datasets.")

    import_cmd = sub.add_parser("import", help="Import an h5ad file and build its FAISS index.")
    import_cmd.add_argument("h5ad_path")
    import_cmd.add_argument("--name", default=None)
    import_cmd.add_argument("--source", default="")
    import_cmd.add_argument("--group", default="regular")
    import_cmd.add_argument("--description", default="")
    import_cmd.add_argument("--tags", default="")

    switch_cmd = sub.add_parser("switch", help="Switch the active dataset.")
    switch_cmd.add_argument("dataset_id")

    delete_cmd = sub.add_parser("delete", help="Delete a dataset and its generated files.")
    delete_cmd.add_argument("dataset_id")

    joint_cmd = sub.add_parser("joint", help="Build a joint FAISS index from multiple datasets.")
    joint_cmd.add_argument("dataset_ids", nargs="+")
    joint_cmd.add_argument("--name", default="Joint dataset")
    joint_cmd.add_argument("--group", default="joint")
    joint_cmd.add_argument("--description", default="")

    args = parser.parse_args()
    manager = DatasetManager()

    if args.command == "list":
        print_json(manager.list_datasets())
    elif args.command == "import":
        tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
        dataset = manager.import_h5ad(
            LocalUpload(Path(args.h5ad_path)),
            name=args.name,
            source=args.source,
            group=args.group,
            description=args.description,
            tags=tags,
        )
        print_json(dataset)
    elif args.command == "switch":
        print_json(manager.set_active_dataset(args.dataset_id))
    elif args.command == "delete":
        print_json(manager.delete_dataset(args.dataset_id))
    elif args.command == "joint":
        print_json(manager.build_joint_index(
            args.dataset_ids,
            name=args.name,
            group=args.group,
            description=args.description,
        ))


if __name__ == "__main__":
    main()
