"""
Step 2 - Build the CFD volume mesh in Fluent Meshing (PyFluent, Fault-tolerant workflow).

Input is the watertight skin from step 1 (aircraft_wrapped.stl, in mm). Fluent
re-meshes that skin, puts a wind-tunnel box around it, grows prism (boundary
layer) cells on the aircraft and fills the rest with poly-hexcore cells.

  ..\\.venv\\Scripts\\python.exe 02_mesh.py            (no GUI)
  ..\\.venv\\Scripts\\python.exe 02_mesh.py --gui      (watch it in the Fluent window)

Output: mesh/aircraft.msh.h5 and mesh/mesh_report.json
Boundary names in the mesh:
  aircraft                      wall
  tunnel-ymax                   inlet face, in front of the nose (nose points +Y)
  tunnel-ymin                   outlet face, behind the tail
  tunnel-xmin/xmax/zmin/zmax    side, top and bottom faces (set as inlets so
                                the angle of attack can be changed in the solver)
"""
import argparse
import json
import sys
import time
from pathlib import Path

import ansys.fluent.core as pf

HERE = Path(__file__).resolve().parent                                 # this case's folder
CFG = json.loads((HERE / "config.json").read_text())                   # mesh sizes, domain, processors
REPORT = json.loads((HERE / "geometry_report.json").read_text())       # aircraft bounds from step 1
OUT_DIR = HERE / "mesh"
MESH_FILE = OUT_DIR / "aircraft.msh.h5"


def log(msg):
    """Timestamped progress line (flush so it shows up live in logs\\mesh_log.txt)."""
    print(f"[mesh {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def check(t, name):
    """Stop if a workflow task did not finish: Fluent otherwise carries on silently with a broken mesh."""
    if t.State() != "Up-to-date":
        raise RuntimeError(f"Task '{name}' did not complete (state={t.State()}). "
                           f"Re-run with --gui to look at it.")


def run_task(wf, name, args=None, update_children=False):
    """Simple workflow task: set arguments, execute."""
    t = wf.TaskObject[name]
    if args:
        t.Arguments.set_state(args)                  # same fields as the task's panel in the GUI
    if update_children:
        t.UpdateChildTasks(SetupTypeChanged=False)   # some tasks add/remove later tasks from their choices
    log(f"-> {name}")
    try:
        t.Execute()
    except RuntimeError as e:
        # the Student licence aborts the task when the mesh outgrows its cell/node cap
        if "license" in str(e).lower():
            raise SystemExit(
                f"'{name}' stopped on a license limit. Ansys Student caps the mesh at ~1M "
                "cells/nodes: raise min_size_mm / aircraft_max_size_mm or lower "
                "boundary_layers in config.json and run again.") from e
        raise
    check(t, name)
    return t


def add_child(wf, name, args):
    """Compound workflow task (sizing, regions, boundary layers): add one child and run it."""
    t = wf.TaskObject[name]
    t.Arguments.set_state(args)
    log(f"-> {name} (+ {args.get('LocalSettingsName') or args.get('MaterialPointsName') or args.get('BLControlName')})")
    t.AddChildAndUpdate()
    check(t, name)
    return t


def domain_box_mm():
    """Wind-tunnel box around the aircraft, config distances (m) -> mm."""
    (xmin, xmax), (ymin, ymax), (zmin, zmax) = REPORT["bounds_m"]
    d = CFG["domain"]
    # the box faces are named by axis (tunnel-ymax = inlet ...), so the frame must be nose +Y, up +Z
    if CFG["axes"]["forward"] != [0, 1, 0] or CFG["axes"]["up"] != [0, 0, 1]:
        sys.exit("02_mesh.py assumes nose +Y and up +Z (config axes). Rotate the STL or edit domain_box_mm().")
    mm = 1000.0                                      # the STL is in mm, so the box must be too
    # upstream = +Y side (in front of the nose), downstream = -Y side (behind the tail)
    return {"SizeRelativeLength": "Directly specify coordinates",
            "Xmin": (xmin - d["lateral_m"]) * mm, "Xmax": (xmax + d["lateral_m"]) * mm,
            "Ymin": (ymin - d["downstream_m"]) * mm, "Ymax": (ymax + d["upstream_m"]) * mm,
            "Zmin": (zmin - d["vertical_m"]) * mm, "Zmax": (zmax + d["vertical_m"]) * mm}


def build(m):
    mc = CFG["mesh"]
    stl = str((HERE / CFG["stl"]).resolve())
    obj = Path(stl).stem                   # Fluent names the object after the file
    box = domain_box_mm()
    wf = m.workflow
    t_start = time.time()

    wf.InitializeWorkflow(WorkflowType="Fault-tolerant Meshing")

    # 1. load the STL and copy it from the CAD tree into the Meshing Model tree
    pm = m.PartManagement
    pm.InputFileChanged(FilePath=stl, IgnoreSolidNames=False, PartPerBody=False)
    m.PMFileManagement.FileManager.LoadFiles()
    pm.Node["Meshing Model"].Copy(Paths=[f"/{obj},1"])
    run_task(wf, "Import CAD and Part Management", {
        "Context": 0, "CreateObjectPer": "Custom", "FMDFileName": stl, "FileLoaded": "yes",
        "ObjectSetting": "DefaultObjectSetting",
        "Options": {"Line": False, "Solid": False, "Surface": False}})

    # 2. external flow inside a wind-tunnel box
    run_task(wf, "Describe Geometry and Flow", {
        "FlowType": "External flow around object", "AddEnclosure": "Yes",
        "CloseCaps": "No", "LocalRefinementRegions": "No"}, update_children=True)
    run_task(wf, "Create External Flow Boundaries", {
        "ExternalBoundariesName": "tunnel", "CreationMethod": "Create new boundary",
        "ExtractionMethod": "surface mesh", "SelectionType": "object",
        "ObjectSelectionList": [obj], "BoundingBoxObject": box})

    # 3. keep sharp edges (trailing edges, tips, tail) in the surface mesh
    run_task(wf, "Extract Edge Features", {
        "ExtractMethodType": "Feature Angle", "FeatureAngleLocal": 40,
        "SelectionType": "object", "ObjectSelectionList": [obj]})

    # 4. fluid region: a point in the air upstream of the nose
    add_child(wf, "Identify Regions", {
        "MaterialPointsName": "fluid-region-1", "NewRegionType": "fluid",
        "MptMethodType": "Numerical Inputs", "SelectionType": "object",
        "ObjectSelectionList": ["tunnel"],
        "X": 0.0, "Y": box["Ymax"] - 0.25 * CFG["domain"]["upstream_m"] * 1000, "Z": 0.0})

    # 5. only the air gets meshed; the inside of the aircraft is "dead"
    run_task(wf, "Update Region Settings", {
        "AllRegionNameList": [obj, "fluid-region-1"],
        "AllRegionMeshMethodList": ["none", "wrap"],
        "AllRegionTypeList": ["dead", "fluid"],
        "AllRegionVolumeFillList": ["none", mc["volume_fill"]],
        "AllRegionLinkedConstructionSurfaceList": ["N/A", "no"],
        "AllRegionOversetComponenList": ["no", "no"],
        "AllRegionFilterCategories": ["2", "1"],
        "AllRegionSourceList": ["object", "mpt"],
        "AllRegionLeakageSizeList": ["none", "none"]})
    run_task(wf, "Choose Mesh Control Options")

    # 6. surface sizing on the aircraft: fine where curved, coarser on flat panels
    add_child(wf, "Add Local Sizing", {
        "LocalSettingsName": "aircraft-curvature", "SelectionType": "object",
        "ObjectSelectionList": [obj],
        "LocalSizeControlParameters": {
            "SizingType": "curvature", "MinSize": mc["min_size_mm"],
            "MaxSize": mc["aircraft_max_size_mm"], "GrowthRate": mc["growth_rate"],
            "CurvatureNormalAngle": mc["curvature_angle_deg"],
            "WrapMin": mc["min_size_mm"], "WrapMax": mc["aircraft_max_size_mm"],
            "WrapCurvatureNormalAngle": mc["curvature_angle_deg"],
            "WrapGrowthRate": mc["growth_rate"]}})
    run_task(wf, "Generate the Surface Mesh")

    # 7. boundary types (values are set in the solver script)
    tunnel = ["tunnel-xmin", "tunnel-xmax", "tunnel-ymin", "tunnel-ymax", "tunnel-zmin", "tunnel-zmax"]
    types = ["pressure-outlet" if z == "tunnel-ymin" else "velocity-inlet" for z in tunnel]
    run_task(wf, "Update Boundaries", {
        "SelectionType": "zone", "BoundaryZoneList": tunnel, "BoundaryZoneTypeList": types,
        "OldBoundaryZoneList": tunnel, "OldBoundaryZoneTypeList": ["wall"] * len(tunnel)})

    # 8. prism layers on the aircraft walls
    add_child(wf, "Add Boundary Layers", {
        "BLControlName": "aircraft-bl", "OffsetMethodType": "uniform",
        "NumberOfLayers": mc["boundary_layers"], "FirstHeight": mc["bl_first_height_mm"],
        "Rate": mc["bl_growth"], "FaceScope": {"GrowOn": "only-walls"}})

    # 9. volume mesh
    run_task(wf, "Generate the Volume Mesh", {
        "AllRegionNameList": ["fluid-region-1"],
        "AllRegionSizeList": [str(mc["max_size_mm"])],
        "AllRegionVolumeFillList": [mc["volume_fill"]],
        "EnableParallel": True})

    # 10. save the mesh (HDF5) for 03_solve.py, plus a small report of the settings used
    m.meshing.File.WriteMesh(FileName=str(MESH_FILE))
    log(f"wrote {MESH_FILE}")

    info = {"mesh_file": str(MESH_FILE), "minutes": round((time.time() - t_start) / 60, 1),
            "settings": mc}
    (OUT_DIR / "mesh_report.json").write_text(json.dumps(info, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gui", action="store_true", help="show the Fluent window")
    ap.add_argument("--connect", help="attach to a running Fluent: text file with ip, port, password")
    args = ap.parse_args()
    OUT_DIR.mkdir(exist_ok=True)

    if args.connect:
        # reuse a Fluent you already opened (its server-info file holds ip, port, password)
        ip, port, pw = Path(args.connect).read_text().split()
        m = pf.connect_to_fluent(ip=ip, port=int(port), password=pw,
                                 cleanup_on_exit=False, start_watchdog=False)
    else:
        log("launching Fluent Meshing ...")
        m = pf.launch_fluent(mode="meshing", precision="double",
                             processor_count=CFG["processors"],
                             ui_mode="gui" if args.gui else "no_gui",
                             cwd=str(OUT_DIR), start_timeout=300)
    try:
        build(m)
    finally:
        # always close a Fluent we launched: Ansys Student allows only one session at a time
        if not args.connect and not args.gui:
            m.exit()


if __name__ == "__main__":
    main()
