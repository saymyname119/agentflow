"""Pure decision function. Repository text never changes the trusted policy."""
import fnmatch
import re
from pathlib import PurePosixPath

from .models import Finding, Policy, Recommendation, Snapshot
from .patches import added_lines

SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rs", ".cpp", ".c"}
SECRET = re.compile(r"(?:AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,})")
RISKY_OPERATION = re.compile(r"\b(?:eval|exec|pickle\.loads)\s*\(|shell\s*=\s*True|\b(?:DROP\s+TABLE|TRUNCATE\s+TABLE)\b", re.IGNORECASE)


def matches(path: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(path.lower(), pattern.lower()) or (
        pattern.startswith("**/") and fnmatch.fnmatchcase(path.lower(), pattern[3:].lower())
    )


def is_test(path: str) -> bool:
    p = PurePosixPath(path.lower())
    return any(x in {"test", "tests", "__tests__"} for x in p.parts) or bool(
        re.search(r"(^test_|_test\.|\.test\.|\.spec\.)", p.name)
    )


def module_key(path: str) -> str:
    stem = PurePosixPath(path.lower()).stem
    return re.sub(r"(^test_|_test$|\.test$|\.spec$)", "", stem)


def evaluate(snapshot: Snapshot, policy: Policy) -> Recommendation:
    findings: list[Finding] = []

    def add(code, message, severity, paths=None):
        findings.append(Finding(code=code, message=message, severity=severity, paths=paths or []))

    if snapshot.state != "open" or snapshot.draft:
        add("not_ready", "Pull request is closed or still a draft.", "block")
    if snapshot.mergeable is not True:
        add("mergeability", "GitHub has not confirmed that this change can merge cleanly.", "block")
    if not snapshot.files_complete or not snapshot.files:
        add("incomplete_files", "Changed-file evidence is incomplete or empty.", "block")

    for required in policy.required_checks:
        checks = [c for c in snapshot.checks if c.name == required.name and c.app_id == required.app_id
                  and c.head_sha == snapshot.head_sha]
        # The adapter requests the latest run for each check name. Ambiguity fails closed.
        if len(checks) != 1 or checks[0].status != "completed" or checks[0].conclusion != "success":
            add("required_ci", f"Required check {required.name!r} from app {required.app_id} is not a confirmed success on this commit.", "block")

    lines = sum(f.additions + f.deletions for f in snapshot.files)
    if lines > policy.max_lines or len(snapshot.files) > policy.max_files:
        add("large_change", "Change exceeds the configured review size limit.", "review")
    sensitive, deleted_tests, missing_patch, secrets, risky_operations, renamed_source = [], [], [], [], [], []
    source_files, test_keys = [], set()
    for file in snapshot.files:
        paths = [file.filename] + ([file.previous_filename] if file.previous_filename else [])
        if any(matches(path, pattern) for path in paths for pattern in policy.sensitive_patterns):
            sensitive.append(file.filename)
        if (file.previous_filename and not is_test(file.previous_filename)
                and PurePosixPath(file.previous_filename).suffix.lower() in SOURCE_SUFFIXES):
            renamed_source.append(file.filename)
        if is_test(file.filename):
            if file.status == "removed" or (file.deletions > 0 and file.additions == 0):
                deleted_tests.append(file.filename)
            elif file.additions > 0:
                test_keys.add(module_key(file.filename))
        elif file.previous_filename and is_test(file.previous_filename):
            deleted_tests.append(file.filename)
        elif PurePosixPath(file.filename).suffix.lower() in SOURCE_SUFFIXES:
            source_files.append(file.filename)
        # Binary files, omitted or truncated patches cannot be treated as inspected.
        if file.patch is None or not file.patch_complete or "... diff too large ..." in (file.patch or ""):
            missing_patch.append(file.filename)
        added = "\n".join(added_lines(file.patch))
        if SECRET.search(added):
            secrets.append(file.filename)
        if not is_test(file.filename) and RISKY_OPERATION.search(added):
            risky_operations.append(file.filename)
    if sensitive:
        add("sensitive_paths", "Security, infrastructure, dependency or data changes require a human review.", "review", sensitive)
    if deleted_tests:
        add("test_removal", "Tests were removed or only deleted from.", "review", deleted_tests)
    if missing_patch:
        add("missing_patch", "Some file contents could not be inspected.", "review", missing_patch)
    if secrets:
        add("secret_material", "Added lines resemble credentials; inspect and rotate any real secret.", "block", secrets)
    if risky_operations:
        add("risky_operation", "Added lines contain dynamic execution or destructive data operations; inspect their intent.", "review", risky_operations)
    if renamed_source:
        add("source_rename", "Renamed source files require review of their original and new roles.", "review", renamed_source)
    uncovered = [p for p in source_files if module_key(p) not in test_keys]
    if uncovered:
        add("test_gap", "Source changes lack a same-module test update. This is a naming heuristic, not coverage proof.", "review", uncovered)
    if not findings:
        add("low_risk", "Small change, required checks passed, and no configured risk signal was found.", "info")
    outcome = "BLOCKED" if any(f.severity == "block" for f in findings) else (
        "REVIEW" if any(f.severity == "review" for f in findings) else "READY")
    return Recommendation(outcome=outcome, policy_version=policy.version, findings=findings,
                          changed_lines=lines, changed_files=len(snapshot.files))
