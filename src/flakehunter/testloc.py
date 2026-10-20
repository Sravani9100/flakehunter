"""Map a JUnit test identifier back to a file and pytest node ID in a checkout."""

from dataclasses import dataclass
from pathlib import PurePosixPath


class TestNotFoundError(LookupError):
    __test__ = False


@dataclass(frozen=True)
class TestLocation:
    __test__ = False

    path: PurePosixPath  # relative to the repository root
    node_id: str
    function: str
    class_name: str | None


def locate_test(root, identifier: str, file_hint: str | None = None) -> TestLocation:
    """Find the test for an identifier like "tests.test_cart::test_total".

    pytest puts the module path (plus any class names) in classname. CI may have run
    pytest from a different directory than the repository root, so leading segments are
    dropped until a file matches.
    """
    module, _, name = identifier.rpartition("::")
    if not name:
        raise TestNotFoundError(f"cannot parse test identifier {identifier!r}")
    parts = module.split(".") if module else []

    if file_hint and (root / file_hint).is_file():
        path = PurePosixPath(file_hint.replace("\\", "/"))
        classes = parts[parts.index(path.stem) + 1 :] if path.stem in parts else []
        return _location(path, classes, name)

    for start in range(len(parts)):
        for end in range(len(parts), start, -1):
            path = PurePosixPath(*parts[start:end]).with_suffix(".py")
            if (root / path).is_file():
                return _location(path, parts[end:], name)
    raise TestNotFoundError(f"no file in the repository matches {identifier!r}")


def _location(path: PurePosixPath, classes: list[str], name: str) -> TestLocation:
    return TestLocation(
        path=path,
        node_id="::".join([str(path), *classes, name]),
        function=name.split("[", 1)[0],  # strip pytest parametrization
        class_name=classes[-1] if classes else None,
    )
