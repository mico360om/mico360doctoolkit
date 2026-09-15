"""Visual page organizer: the thumbnail-grid dialog (reorder / rotate / delete /
split) and the pdf_organize "visual" runner that applies its plan.

Run:  python tests/page_organizer_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

failures: list[str] = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def _make_pdf(path: Path, pages: int) -> None:
    import fitz
    d = fitz.open()
    for i in range(pages):
        pg = d.new_page()
        pg.insert_text((72, 100), f"PAGE {i + 1}")
    d.save(str(path))
    d.close()


def _texts(path: Path) -> list[str]:
    import fitz
    r = fitz.open(str(path))
    out = [pg.get_text().strip().replace("\n", " ") for pg in r]
    r.close()
    return out


def _rots(path: Path) -> list[int]:
    import fitz
    r = fitz.open(str(path))
    out = [pg.rotation for pg in r]
    r.close()
    return out


class _Rep:
    def __call__(self, *a, **k):
        pass


def main() -> int:
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from mico360.core import processors as P
    from mico360.core.tools import TOOLS_BY_ID
    from mico360.ui.page_organizer import PageOrganizerDialog, render_page_thumbs

    td = Path(tempfile.mkdtemp(prefix="mico_pageorg_"))
    src = td / "doc.pdf"
    _make_pdf(src, 5)
    rep = _Rep()

    # ---------- tool registry ----------
    print("--- registry ---")
    org = TOOLS_BY_ID["pdf_organize"]
    ops = dict(next(o for o in org.options if o.key == "operation").choices)
    check("Organize tool has a 'visual' operation", "visual" in ops, str(list(ops)))
    plan_opt = next((o for o in org.options if o.key == "plan"), None)
    check("Organize tool has a page_plan option", plan_opt is not None
          and plan_opt.kind == "page_plan")

    # ---------- thumbnail rendering ----------
    print("--- rendering ---")
    thumbs = render_page_thumbs(src)
    check("renders one thumbnail per page", len(thumbs) == 5, str(len(thumbs)))
    check("thumbnails are non-empty pixmaps",
          all(not p.isNull() and p.width() > 0 for p in thumbs))
    check("missing file renders nothing (no crash)",
          render_page_thumbs(td / "nope.pdf") == [])

    # ---------- dialog default state ----------
    print("--- dialog ---")
    dlg = PageOrganizerDialog(src)
    check("grid has one tile per page", dlg.grid.count() == 5, str(dlg.grid.count()))
    pl = dlg.plan()
    check("default plan is one group of all pages in order",
          pl["n_src"] == 5 and len(pl["groups"]) == 1
          and [i["src"] for i in pl["groups"][0]] == [0, 1, 2, 3, 4], str(pl))
    check("default rotations are all zero",
          all(i["rotate"] == 0 for i in pl["groups"][0]))

    # ---------- rotate ----------
    dlg.grid.item(1).setSelected(True)
    dlg._rotate_cw()
    dlg.grid.item(1).setSelected(False)
    dlg.grid.item(3).setSelected(True)
    dlg._rotate_ccw()
    pg = dlg.plan()["groups"][0]
    check("rotate right sets +90 on the selected page", pg[1]["rotate"] == 90, str(pg[1]))
    check("rotate left sets 270 on the selected page", pg[3]["rotate"] == 270, str(pg[3]))

    # ---------- delete ----------
    dlg.grid.clearSelection()
    dlg.grid.item(4).setSelected(True)
    dlg._delete_selected()
    pl = dlg.plan()
    kept = [i["src"] for g in pl["groups"] for i in g]
    check("delete removes the page from the plan", kept == [0, 1, 2, 3], str(kept))
    check("grid tile count drops after delete", dlg.grid.count() == 4)

    # ---------- split ----------
    dlg.grid.clearSelection()
    dlg.grid.item(1).setSelected(True)     # split after the 2nd tile
    dlg._add_split()
    pl = dlg.plan()
    check("split produces two groups", len(pl["groups"]) == 2, str(len(pl["groups"])))
    check("split boundary is correct",
          [i["src"] for i in pl["groups"][0]] == [0, 1]
          and [i["src"] for i in pl["groups"][1]] == [2, 3], str(pl["groups"]))
    check("a divider tile was inserted", dlg.grid.count() == 5)   # 4 pages + 1 split

    # a split never leads, and two can't stack
    dlg.grid.clearSelection()
    dlg._add_split()                        # nothing selected -> append at end
    before = dlg.grid.count()
    last = dlg.grid.item(dlg.grid.count() - 1)
    last.setSelected(True)
    dlg._add_split()                        # would stack on a divider -> ignored
    check("won't stack two split markers", dlg.grid.count() == before, str(dlg.grid.count()))

    # ---------- reset ----------
    dlg.reset()
    pl = dlg.plan()
    check("reset restores all pages, one group, no rotation",
          len(pl["groups"]) == 1 and len(pl["groups"][0]) == 5
          and all(i["rotate"] == 0 for i in pl["groups"][0]))

    # ---------- round-trip through a rebuilt dialog ----------
    seed = {"n_src": 5, "groups": [[{"src": 2, "rotate": 90}], [{"src": 0, "rotate": 0}]]}
    dlg2 = PageOrganizerDialog(src, plan=seed)
    check("a plan reloads into the grid (pages + split)",
          dlg2.plan()["groups"] == seed["groups"], str(dlg2.plan()["groups"]))

    # ---------- runner: apply a full plan ----------
    print("--- runner ---")
    plan = {"n_src": 5, "groups": [
        [{"src": 2, "rotate": 0}, {"src": 0, "rotate": 90}],
        [{"src": 4, "rotate": 0}]]}
    outs = P.pdf_organize(src, td / "out", {"operation": "visual", "plan": plan,
                                            "overwrite": True}, rep)
    check("split plan writes one file per group", len(outs) == 2, str([o.name for o in outs]))
    check("reorder + delete applied (file 1 = pages 3,1)",
          _texts(outs[0]) == ["PAGE 3", "PAGE 1"], str(_texts(outs[0])))
    check("per-page rotation applied", _rots(outs[0]) == [0, 90], str(_rots(outs[0])))
    check("second split file holds the remaining page",
          _texts(outs[1]) == ["PAGE 5"], str(_texts(outs[1])))

    # single group -> single "_organized" file, no _part suffix
    single = {"n_src": 5, "groups": [[{"src": 0, "rotate": 0}, {"src": 1, "rotate": 0}]]}
    outs = P.pdf_organize(src, td / "out2", {"operation": "visual", "plan": single,
                                             "overwrite": True}, rep)
    check("single group => one file named _organized",
          len(outs) == 1 and outs[0].name.endswith("_organized.pdf"), str(outs[0].name))

    # ---------- runner guards ----------
    print("--- runner guards ---")
    from mico360.core.util import ProcessError

    def _expect_error(label, opt):
        try:
            P.pdf_organize(src, td / "err", opt, rep)
            check(label, False, "no error raised")
        except ProcessError as e:
            check(label, True, str(e)[:60])
        except Exception as e:      # noqa: BLE001
            check(label, False, f"wrong error: {type(e).__name__}: {e}")

    _expect_error("empty plan is a clear error",
                  {"operation": "visual", "plan": {"n_src": 5, "groups": []}})
    _expect_error("page-count mismatch is caught",
                  {"operation": "visual",
                   "plan": {"n_src": 9, "groups": [[{"src": 0, "rotate": 0}]]}})
    _expect_error("out-of-range page index is caught",
                  {"operation": "visual",
                   "plan": {"n_src": 5, "groups": [[{"src": 99, "rotate": 0}]]}})

    # existing operations still work (no regression)
    outs = P.pdf_organize(src, td / "rot", {"operation": "rotate", "angle": 90,
                                            "pages": "all", "overwrite": True}, rep)
    check("classic 'rotate' operation still works",
          len(outs) == 1 and _rots(outs[0]) == [90] * 5, str(_rots(outs[0])))

    # ---------- options widget wiring ----------
    print("--- options widget ---")
    from mico360.ui.options_widget import OptionsWidget, _PagePlanField
    ow = OptionsWidget(org)
    ow.set_file_getter(lambda: src)
    ctrl = ow._controls["plan"]
    check("page_plan builds a _PagePlanField", isinstance(ctrl, _PagePlanField))
    check("plan value starts as None", ow.values().get("plan") is None)
    check("page_plan key is excluded from saving", "plan" in ow._no_save_keys)
    # simulate the dialog result being stored
    ctrl._plan = plan
    ctrl._target = src
    check("stored plan is returned by values()", ow.values().get("plan") == plan)
    saved = {k: v for k, v in ow.values().items() if k not in ow._no_save_keys}
    check("save() would not persist the plan", "plan" not in saved)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED: {', '.join(failures)}")
        return 1
    print("Page organizer: ALL PASSED")
    return 0


if __name__ == "__main__":
    _rc = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_rc if isinstance(_rc, int) else 0)
