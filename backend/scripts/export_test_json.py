"""Export the test project to JSON for API testing."""

import json

from scripts.test_building import make_test_project


def main() -> None:
    project = make_test_project()
    with open("/tmp/test_project.json", "w", encoding="utf-8") as f:
        json.dump(project.model_dump(), f, indent=2, ensure_ascii=False)
    print("Saved to /tmp/test_project.json")


if __name__ == "__main__":
    main()
