"""GitHub's file patch contains unified-diff hunks, not file headers."""


def added_lines(patch):
    # splitlines() also splits Unicode separators that can occur inside one code line.
    return [line[1:] for line in (patch or "").split("\n") if line.startswith("+")]


def patch_is_complete(file):
    if file.patch is None:
        return False
    lines = file.patch.split("\n")
    return (sum(line.startswith("+") for line in lines) == file.additions
            and sum(line.startswith("-") for line in lines) == file.deletions)
