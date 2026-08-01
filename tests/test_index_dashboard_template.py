"""Audit T48 regression tests for the extracted index-dashboard template.

scripts/xfp/lib/index_dashboard_template.py holds the HTML/React template that
was moved VERBATIM out of scripts/xfp/build_index_dashboard.py (pre-extraction
lines 861-4383) on 2026-08-01 (T48 second attempt). Contract locked here:

  1. The template stays a single plain string CONSTANT (never an f-string):
     zero interpolation points, zero free names — so render_app()'s parameter
     set is exactly the literal's free-variable set (both empty).
  2. The builder's call site passes exactly that (empty) parameter set.
  3. The substitution interface is the 12 named __TOKEN__ markers: the token
     set in the template equals the token set the builder's .replace() chain
     substitutes, each token appears exactly once, and a synthetic fixed-
     fixture substitution leaves no marker behind (the offline analog of the
     output A/B — no ESPN, no caches, no clock).

The one-time SOURCE-IDENTITY proof (AST-extracted literal from
`git show 8dc9200:scripts/xfp/build_index_dashboard.py` == the literal here,
byte-for-byte — 201,407 chars / 204,573 UTF-8 bytes on both sides, sha256
7e501a8d30bd80d41fdb1664a9ff576107e3b4908480c96016104a8a0bd2da22) is recorded
in the template module's docstring, deliberately NOT re-run here: it depends
on the git HEAD of the extraction moment.

No content hash is locked: legitimate future template edits must not fail
these tests — only structural drift (interpolation sneaking in, parameter/
call-site divergence, or a token-interface mismatch) should.
"""
import ast
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PY = ROOT / "scripts" / "xfp" / "lib" / "index_dashboard_template.py"
BUILDER_PY = ROOT / "scripts" / "xfp" / "build_index_dashboard.py"

TOKEN_RE = re.compile(r"__[A-Z][A-Z0-9_]*__")


def _read_lf(path: Path) -> str:
    # core.autocrlf=true checks files out with CRLF; git blobs are LF.
    return path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")


def _render_app_fn(tree: ast.Module) -> ast.FunctionDef:
    fns = [n for n in tree.body
           if isinstance(n, ast.FunctionDef) and n.name == "render_app"]
    assert len(fns) == 1, "expected exactly one render_app in the template module"
    return fns[0]


def _load_template_module():
    spec = importlib.util.spec_from_file_location(
        "_index_dashboard_template_under_test", TEMPLATE_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_template_is_a_plain_constant_with_no_free_variables():
    """The literal must stay an ast.Constant — never a JoinedStr (f-string) —
    with zero FormattedValue interpolation points and zero free names, and
    render_app's parameter set must equal that (empty) free-name set."""
    tree = ast.parse(_read_lf(TEMPLATE_PY))
    fn = _render_app_fn(tree)

    assert len(fn.body) == 1 and isinstance(fn.body[0], ast.Return), \
        "render_app body must be exactly one return statement"
    val = fn.body[0].value
    assert isinstance(val, ast.Constant) and isinstance(val.value, str), (
        f"template literal must be a plain string Constant, got "
        f"{type(val).__name__} — if interpolation is being added, T48's "
        f"free-variable contract must be re-derived, not silently broken")

    free = {n.id for sub in ast.walk(val) if isinstance(sub, (ast.FormattedValue, ast.Name))
            for n in ast.walk(sub) if isinstance(n, ast.Name)}
    assert free == set(), f"template literal grew free variables: {sorted(free)}"

    params = ([a.arg for a in fn.args.posonlyargs] + [a.arg for a in fn.args.args]
              + [a.arg for a in fn.args.kwonlyargs]
              + ([fn.args.vararg.arg] if fn.args.vararg else [])
              + ([fn.args.kwarg.arg] if fn.args.kwarg else []))
    assert set(params) == free == set(), (
        f"render_app parameters {params} must equal the literal's free-name "
        f"set {sorted(free)}")


def test_builder_call_site_passes_exactly_the_parameter_set():
    """HTML_TEMPLATE in the builder must be assigned from a render_app() call
    whose arguments are exactly render_app's (empty) parameter set."""
    tree = ast.parse(_read_lf(BUILDER_PY))
    assigns = [n for n in tree.body
               if isinstance(n, ast.Assign)
               and len(n.targets) == 1
               and isinstance(n.targets[0], ast.Name)
               and n.targets[0].id == "HTML_TEMPLATE"]
    assert len(assigns) == 1, "expected exactly one module-level HTML_TEMPLATE assign"
    call = assigns[0].value
    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name) \
        and call.func.id == "render_app", \
        "HTML_TEMPLATE must be assigned from render_app(...)"
    assert call.args == [] and call.keywords == [], (
        "call site passes arguments but render_app's parameter set is empty — "
        "the free-variable contract and this test must be updated together")


def test_token_interface_in_sync_and_synthetic_substitution_is_total():
    """Fixed-fixture version of the A/B: the rendered template must carry
    exactly the token interface the builder's .replace() chain substitutes —
    each token once — and substituting synthetic values must leave no marker
    behind. Runs fully offline (the template module imports nothing)."""
    html = _load_template_module().render_app()
    assert isinstance(html, str) and html.startswith("<!DOCTYPE html>")

    template_tokens = set(TOKEN_RE.findall(html))
    chain_tokens = set(re.findall(r"\.replace\('(__[A-Z][A-Z0-9_]*__)'",
                                  _read_lf(BUILDER_PY)))
    assert chain_tokens, "builder .replace() token chain not found"
    assert template_tokens == chain_tokens, (
        f"token interface out of sync — only in template: "
        f"{sorted(template_tokens - chain_tokens)}, only in builder chain: "
        f"{sorted(chain_tokens - template_tokens)} (a template token with no "
        f".replace() ships literally into the published HTML)")

    for tok in sorted(template_tokens):
        assert html.count(tok) == 1, f"{tok} appears {html.count(tok)}x, expected once"

    # synthetic values must not themselves match TOKEN_RE (strip the dunders)
    substituted = html
    for tok in sorted(template_tokens):
        substituted = substituted.replace(tok, f"<<synth:{tok.strip('_').lower()}>>")
    assert not TOKEN_RE.findall(substituted), (
        f"unsubstituted markers remain: {sorted(set(TOKEN_RE.findall(substituted)))}")
    for tok in sorted(template_tokens):
        assert substituted.count(f"<<synth:{tok.strip('_').lower()}>>") == 1

    # determinism: a second render is the identical string
    assert _load_template_module().render_app() == html
