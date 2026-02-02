import fnmatch
from collections import OrderedDict
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

try:
    # Optional: provides regex timeouts to mitigate ReDoS risk.
    import regex as regexlib  # type: ignore
except Exception:  # pragma: no cover
    regexlib = None  # type: ignore

# Configure logging with basic setup
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# Skills Matching Data Structures
# =============================================================================

@dataclass
class SkillTriggers:
    """Trigger configuration for a skill."""

    keywords: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)  # regex strings
    files: list[str] = field(default_factory=list)  # glob patterns
    always: bool = False
    priority: int = 50  # 0-100, higher = more important


@dataclass
class Skill:
    """Parsed skill definition."""

    name: str
    description: str
    triggers: SkillTriggers
    content: str
    path: str
    mtime: float


@dataclass
class MatchedSkill:
    """A skill that matched with scoring details."""

    skill: Skill
    score: int
    matched_by: list[str]


# =============================================================================
# Skills Matcher
# =============================================================================

class SkillsMatcher:
    """Match user prompts against skill triggers.
    
    Scoring Logic:
    - Base Priority: 0-100 (default 50)
    - Always: +1000
    - File Match: +100 per matched file
    - Pattern Match: +50 per matched regex
    - Keyword Match: +10 per matched keyword
    
    Total Score = Priority + Matches

    Regex patterns are cached with an LRU limit.
    """

    CACHE_TTL = 60.0  # seconds

    # Safety/performance limits.
    MAX_SKILL_FILES_PER_DIR = 500
    MAX_SKILLS_TOTAL = 2000
    MAX_KEYWORDS_PER_SKILL = 100
    MAX_PATTERNS_PER_SKILL = 50
    MAX_FILE_PATTERNS_PER_SKILL = 50
    MAX_SKILL_FILE_BYTES = 1_000_000  # ~1MB hard cap for a single SKILL.md

    MAX_PROMPT_CHARS = 20000
    MAX_REGEX_PROMPT_CHARS = 8000
    MAX_FILE_CONTEXT = 200
    MAX_TOKEN_COUNT = 5000

    MAX_PATTERN_LENGTH = 512
    MAX_COMPILED_PATTERNS = 512  # LRU cache size for regex patterns
    REGEX_TIMEOUT_S = 0.05

    def __init__(self, skills_dirs: list[str] | None = None):
        self._skills_dirs = skills_dirs or []
        self._skills_cache: dict[str, Skill] = {}
        self._skills_by_path: dict[str, Skill] = {}
        self._last_scan: float = 0.0
        self._last_dirs: tuple[str, ...] = ()
        # LRU cache for compiled regex patterns (bounded size)
        self._compiled_patterns: OrderedDict[str, Any] = OrderedDict()
        self._warned_regex_missing: bool = False

    def _discover_dirs(self, project_root: str | None = None) -> list[str]:
        """Discover skills directories in priority order."""
        dirs: list[str] = []
        seen: set[str] = set()

        def _add_dir(p: Path) -> None:
            try:
                expanded = p.expanduser()
            except Exception:
                expanded = p
            try:
                resolved = str(expanded.resolve())
            except Exception:
                resolved = str(expanded)

            if resolved in seen:
                return
            if os.path.isdir(resolved):
                seen.add(resolved)
                dirs.append(resolved)

        # Project-level: {project_root}/.trellis/skills/
        if project_root:
            _add_dir(Path(project_root) / ".trellis" / "skills")

        # User-level: ~/.cursor/skills/
        _add_dir(Path.home() / ".cursor" / "skills")

        # System-level: ~/.claude/skills/
        _add_dir(Path.home() / ".claude" / "skills")

        return dirs

    def _is_within_dir(self, base_dir: str, candidate_path: str) -> bool:
        """Return True if candidate_path resolves within base_dir.
        
        Mitigates path traversal via symlinks/junctions inside skills directories.
        """
        try:
            base = os.path.normcase(os.path.abspath(os.path.realpath(base_dir)))
            cand = os.path.normcase(os.path.abspath(os.path.realpath(candidate_path)))
            return os.path.commonpath([base, cand]) == base
        except Exception:
            return False

    def _iter_skill_files(self, skills_dir: str) -> list[str]:
        """Find skill definition files under a directory."""
        skill_files: list[str] = []
        base_dir = str(skills_dir)
        try:
            for root, dirs, files in os.walk(skills_dir):
                # Avoid scanning common large/irrelevant directories if present.
                dirs[:] = [
                    d
                    for d in dirs
                    if d not in {".git", "__pycache__", "node_modules", ".venv", "venv"}
                ]
                dirs.sort()
                files.sort()
                for filename in files:
                    lower = filename.lower()
                    if lower == "skill.md" or lower.endswith(".skill.md"):
                        candidate = os.path.join(root, filename)
                        if not self._is_within_dir(base_dir, candidate):
                            continue
                        skill_files.append(candidate)
                        if len(skill_files) >= self.MAX_SKILL_FILES_PER_DIR:
                            return skill_files
        except Exception:
            # Best-effort scanning; ignore inaccessible dirs.
            return []
        return skill_files

    def _extract_frontmatter(self, raw: str) -> tuple[str, str] | None:
        """Extract YAML frontmatter and body from markdown."""
        # Frontmatter must start at file beginning.
        lines = raw.splitlines(keepends=True)
        if not lines or lines[0].strip() != "---":
            return None

        end_idx: int | None = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break

        if end_idx is None:
            return None

        frontmatter = "".join(lines[1:end_idx])
        body = "".join(lines[end_idx + 1 :]).lstrip("\r\n")
        return frontmatter, body

    def _normalize_name_from_path(self, path: str) -> str:
        p = Path(path)
        filename = p.name.lower()
        if filename == "skill.md":
            return p.parent.name
        stem = p.stem
        if stem.lower().endswith(".skill"):
            stem = stem[: -len(".skill")]
        return stem

    def _ensure_str_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                if item is None:
                    continue
                out.append(str(item))
            return out
        return [str(value)]

    def _clean_list(self, values: list[str], max_items: int) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for v in values:
            s = str(v).strip()
            if not s:
                continue
            if s in seen:
                continue
            seen.add(s)
            out.append(s)
            if len(out) >= max_items:
                break
        return out

    def _truncate_text(self, text: str, max_chars: int) -> str:
        if not text:
            return ""
        if len(text) <= max_chars:
            return text
        return text[:max_chars]

    def _tokenize(self, text_lower: str) -> set[str]:
        tokens: set[str] = set()
        if not text_lower:
            return tokens
        for m in re.finditer(r"\b\w+\b", text_lower):
            tokens.add(m.group(0))
            if len(tokens) >= self.MAX_TOKEN_COUNT:
                break
        return tokens

    def _prune_compiled_patterns(self, used_patterns: set[str]) -> None:
        if not self._compiled_patterns:
            return
        for key in list(self._compiled_patterns.keys()):
            if key not in used_patterns:
                del self._compiled_patterns[key]
        while len(self._compiled_patterns) > self.MAX_COMPILED_PATTERNS:
            self._compiled_patterns.popitem(last=False)

    def _compile_pattern(self, pat_str: str) -> Any | None:
        compiled = self._compiled_patterns.get(pat_str)
        if compiled is not None:
            self._compiled_patterns.move_to_end(pat_str)
            return compiled

        try:
            if regexlib is None:
                # Defensive default: do not evaluate potentially-catastrophic regexes
                # without a timeout mechanism.
                if not self._warned_regex_missing:
                    logger.warning(
                        "Python 'regex' module not available; disabling regex skill triggers to mitigate ReDoS."
                    )
                    self._warned_regex_missing = True
                return None
            compiled = regexlib.compile(pat_str, flags=regexlib.IGNORECASE)
        except Exception as e:
            logger.warning("Invalid regex pattern in skill trigger. pattern=%s error=%s", pat_str, e)
            return None

        self._compiled_patterns[pat_str] = compiled
        self._compiled_patterns.move_to_end(pat_str)
        if len(self._compiled_patterns) > self.MAX_COMPILED_PATTERNS:
            self._compiled_patterns.popitem(last=False)
        return compiled

    def _extract_keywords_from_description(self, description: str) -> list[str]:
        """Fallback: extract keywords from description text."""
        if not description:
            return []

        stopwords = {
            "a", "an", "and", "are", "as", "at", "based", "be", "by", "can",
            "do", "does", "for", "from", "how", "i", "if", "in", "into", "is",
            "it", "like", "need", "of", "on", "or", "should", "that", "the",
            "then", "this", "to", "used", "use", "via", "we", "what", "when",
            "where", "with",
        }

        tokens = re.findall(r"\b\w+\b", description.lower())
        seen: set[str] = set()
        keywords: list[str] = []
        for t in tokens:
            if len(t) < 2:
                continue
            if t.isdigit():
                continue
            if t in stopwords:
                continue
            if t in seen:
                continue
            seen.add(t)
            keywords.append(t)
            if len(keywords) >= 25:
                break
        return keywords

    def _parse_skill(self, path: str) -> Skill | None:
        """Parse a SKILL.md file."""
        if yaml is None:
            logger.warning("PyYAML not available; cannot parse skills. path=%s", path)
            return None

        try:
            size = os.path.getsize(path)
        except Exception:
            size = None
        if size is not None and size > self.MAX_SKILL_FILE_BYTES:
            logger.warning("Skill file too large; skipping. path=%s size=%s", path, size)
            return None

        try:
            raw = Path(path).read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Failed reading skill file. path=%s error=%s", path, e)
            return None

        extracted = self._extract_frontmatter(raw)
        if not extracted:
            # Malformed / missing frontmatter; skip per requirements.
            return None

        frontmatter_raw, body = extracted
        try:
            fm = yaml.safe_load(frontmatter_raw) or {}
        except Exception as e:
            logger.warning("Malformed YAML in skill file. path=%s error=%s", path, e)
            return None

        if not isinstance(fm, dict):
            return None

        description = str(fm.get("description") or "")

        triggers_raw = fm.get("triggers")
        has_explicit_triggers = triggers_raw is not None
        if not isinstance(triggers_raw, dict):
            triggers_raw = {}

        always = bool(triggers_raw.get("always", fm.get("alwaysApply", False)))
        try:
            priority = int(triggers_raw.get("priority", 50))
        except Exception:
            priority = 50
        priority = max(0, min(100, priority))

        keywords = self._clean_list(
            self._ensure_str_list(triggers_raw.get("keywords")),
            self.MAX_KEYWORDS_PER_SKILL,
        )
        patterns = self._clean_list(
            self._ensure_str_list(triggers_raw.get("patterns")),
            self.MAX_PATTERNS_PER_SKILL,
        )
        files = self._clean_list(
            self._ensure_str_list(triggers_raw.get("files")),
            self.MAX_FILE_PATTERNS_PER_SKILL,
        )

        triggers = SkillTriggers(
            keywords=keywords,
            patterns=patterns,
            files=files,
            always=always,
            priority=priority,
        )

        # Backward compat: skills without `triggers` field use description for keyword extraction.
        if not has_explicit_triggers:
            triggers.keywords = self._extract_keywords_from_description(description)

        name = str(fm.get("name") or "").strip() or self._normalize_name_from_path(path)
        try:
            mtime = os.path.getmtime(path)
        except Exception:
            mtime = 0.0

        return Skill(
            name=name,
            description=description,
            triggers=triggers,
            content=body.strip(),
            path=path,
            mtime=mtime,
        )

    def load_skills(self, project_root: str | None = None) -> None:
        """Scan directories and load skills (with caching)."""
        skills_dirs = self._skills_dirs or self._discover_dirs(project_root)
        dirs_key = tuple(skills_dirs)

        now = time.time()
        should_rescan = (now - self._last_scan) >= self.CACHE_TTL or dirs_key != self._last_dirs

        # Invalidate early if any known skill file changed/vanished.
        if not should_rescan and self._skills_by_path:
            for skill in self._skills_by_path.values():
                try:
                    mtime = os.path.getmtime(skill.path)
                except Exception:
                    should_rescan = True
                    break
                if mtime != skill.mtime:
                    should_rescan = True
                    break

            if not should_rescan:
                return

        new_by_name: dict[str, Skill] = {}
        new_by_path: dict[str, Skill] = {}

        for skills_dir in skills_dirs:
            for path in self._iter_skill_files(skills_dir):
                try:
                    mtime = os.path.getmtime(path)
                except Exception:
                    continue

                cached = self._skills_by_path.get(path)
                if cached and cached.mtime == mtime:
                    parsed = cached
                else:
                    parsed = self._parse_skill(path)

                if parsed is None:
                    continue

                new_by_path[path] = parsed
                if len(new_by_path) >= self.MAX_SKILLS_TOTAL:
                    logger.warning(
                        "Skill cache capped at %s entries; additional skills skipped.",
                        self.MAX_SKILLS_TOTAL,
                    )
                    break

                # Conflict resolution: earlier directory in discovery order wins.
                if parsed.name not in new_by_name:
                    new_by_name[parsed.name] = parsed

            if len(new_by_path) >= self.MAX_SKILLS_TOTAL:
                break

        self._skills_cache = new_by_name
        self._skills_by_path = new_by_path
        self._last_scan = now
        self._last_dirs = dirs_key

        # Prevent unbounded growth: keep compiled regexes only for currently-loaded patterns.
        if self._compiled_patterns:
            compiled_keys = set(self._compiled_patterns.keys())
            used_patterns: set[str] = set()
            for s in self._skills_cache.values():
                for p in s.triggers.patterns:
                    if not p:
                        continue
                    p_str = str(p)
                    if p_str in compiled_keys:
                        used_patterns.add(p_str)
            self._prune_compiled_patterns(used_patterns)

    def _match_keywords(self, prompt_lower: str, tokens: set[str], keywords: list[str]) -> list[str]:
        """Check keyword matches (case-insensitive, word boundary)."""
        if not prompt_lower or not keywords:
            return []

        matched: list[str] = []
        for kw in keywords[: self.MAX_KEYWORDS_PER_SKILL]:
            kw_str = str(kw).strip()
            if not kw_str:
                continue
            kw_lower = kw_str.lower()
            if re.fullmatch(r"\w+", kw_lower):
                if kw_lower in tokens:
                    matched.append(kw_str)
            else:
                if re.search(r"\b" + re.escape(kw_lower) + r"\b", prompt_lower):
                    matched.append(kw_str)
        return matched

    def _match_patterns(self, prompt: str, patterns: list[str]) -> list[str]:
        """Check regex pattern matches."""
        if not prompt or not patterns:
            return []

        prompt_str = self._truncate_text(str(prompt), self.MAX_REGEX_PROMPT_CHARS)
        matched: list[str] = []
        for pat in patterns[: self.MAX_PATTERNS_PER_SKILL]:
            pat_str = str(pat).strip()
            if not pat_str:
                continue

            if len(pat_str) > self.MAX_PATTERN_LENGTH:
                logger.warning("Regex pattern too long; skipping. pattern_prefix=%s", pat_str[:80])
                continue

            compiled = self._compile_pattern(pat_str)
            if compiled is None:
                continue

            try:
                if regexlib is not None:
                    if compiled.search(prompt_str, timeout=self.REGEX_TIMEOUT_S):
                        matched.append(pat_str)
                else:
                    if compiled.search(prompt_str):
                        matched.append(pat_str)
            except TimeoutError:
                logger.warning("Regex timeout in skill trigger. pattern_prefix=%s", pat_str[:80])
            except Exception as e:
                logger.warning("Regex matching failed in skill trigger. pattern_prefix=%s error=%s", pat_str[:80], e)
        return matched

    def _normalize_match_path(self, path: str) -> str:
        # Normalize separators to forward slashes for consistent glob matching.
        s = str(path).replace("\\", "/")
        while s.startswith("./"):
            s = s[2:]
        if s.startswith("/"):
            s = s[1:]
        return s

    def _normalize_file_context(self, files: list[str], project_root: str | None) -> list[str]:
        out: list[str] = []
        base = str(project_root) if project_root else None
        for f in files[: self.MAX_FILE_CONTEXT]:
            if f is None:
                continue
            s = str(f).strip()
            if not s:
                continue
            if base and os.path.isabs(s):
                try:
                    s = os.path.relpath(s, base)
                except Exception:
                    pass
            s = self._normalize_match_path(s)
            if s:
                out.append(s)
        return out

    def _match_files(self, norm_files_lower: list[str], file_patterns: list[str]) -> list[str]:
        """Check file glob pattern matches."""
        if not norm_files_lower or not file_patterns:
            return []

        matched_patterns: list[str] = []

        for pat in file_patterns[: self.MAX_FILE_PATTERNS_PER_SKILL]:
            pat_str = str(pat).strip()
            if not pat_str:
                continue
            norm_pat = self._normalize_match_path(pat_str).lower()
            for f in norm_files_lower:
                if fnmatch.fnmatchcase(f, norm_pat):
                    matched_patterns.append(pat_str)
                    break

        # Deduplicate while preserving order.
        seen: set[str] = set()
        out: list[str] = []
        for p in matched_patterns:
            if p in seen:
                continue
            seen.add(p)
            out.append(p)
        return out

    def get_skill(self, name: str, project_root: str | None = None) -> Skill | None:
        """Get a specific skill by name."""
        self.load_skills(project_root)
        return self._skills_cache.get(name)

    def match(
        self,
        prompt: str,
        file_context: list[str] | None = None,
        project_root: str | None = None,
    ) -> list[MatchedSkill]:
        """Find matching skills sorted by score."""
        self.load_skills(project_root)

        prompt_str = str(prompt or "").strip()
        
        # Early optimization: if prompt is empty, only check for 'always: true' skills
        if not prompt_str:
            matches: list[MatchedSkill] = []
            for skill in self._skills_cache.values():
                if skill.triggers.always:
                    score = skill.triggers.priority + 1000
                    matches.append(MatchedSkill(skill=skill, score=score, matched_by=["always"]))
            matches.sort(key=lambda m: (-m.score, -m.skill.triggers.priority, m.skill.name))
            return matches

        prompt_for_keywords = self._truncate_text(prompt_str, self.MAX_PROMPT_CHARS)
        prompt_lower = prompt_for_keywords.lower()
        tokens = self._tokenize(prompt_lower)

        files = self._normalize_file_context(list(file_context or []), project_root)
        norm_files_lower = [f.lower() for f in files]

        matches: list[MatchedSkill] = []

        for skill in self._skills_cache.values():
            matched_by: list[str] = []

            # 1) always
            if skill.triggers.always:
                matched_by.append("always")
            else:
                # 2) file patterns
                for p in self._match_files(norm_files_lower, skill.triggers.files):
                    matched_by.append(f"file:{p}")
                # 3) regex patterns
                for p in self._match_patterns(prompt_str, skill.triggers.patterns):
                    matched_by.append(f"pattern:{p}")
                # 4) keyword matches
                for k in self._match_keywords(prompt_lower, tokens, skill.triggers.keywords):
                    matched_by.append(f"keyword:{k}")

            if not matched_by:
                continue

            score = skill.triggers.priority
            if skill.triggers.always:
                score += 1000
            else:
                score += sum(100 for m in matched_by if m.startswith("file:"))
                score += sum(50 for m in matched_by if m.startswith("pattern:"))
                score += sum(10 for m in matched_by if m.startswith("keyword:"))

            matches.append(MatchedSkill(skill=skill, score=score, matched_by=matched_by))

        matches.sort(key=lambda m: (-m.score, -m.skill.triggers.priority, m.skill.name))
        return matches

