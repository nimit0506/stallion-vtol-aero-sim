"""
Step 1 - Repair and shrink-wrap the aircraft STL into ONE watertight skin for Fluent Meshing.

  ..\\.venv\\Scripts\\python.exe 01_prep_stl.py --units mm --close-mm 24

What it does
  * reports facet count, bounding box, units guess, open (hole) edges,
    non-manifold edges and number of disconnected bodies
  * merges duplicate vertices, drops degenerate / duplicate facets, fills small holes
    (diagnostics + the reference-value estimates; the wrap below starts from the raw facets)
  * shrink-wraps the whole assembly on a voxel grid: overlapping parts, internal parts,
    holes and gaps disappear, and one closed manifold outer skin comes out (shrink_wrap())
  * decimates the skin to ~300k facets (Ansys Student rejects much bigger surfaces)
  * works out the units (mm / inch / m) and always writes the STL in mm,
    which is what Fluent Meshing assumes for STL files
  * writes  aircraft_wrapped.stl  and  geometry_report.json  (sizes in metres,
    used by steps 2 and 3)

Facet repair alone can't fix an assembly of intersecting parts; the voxel wrap can.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pyvista as pv

HERE = Path(__file__).resolve().parent
DEFAULT_IN = HERE.parent / "geometry" / "source" / "stallion_v2_assembled.stl"


def edge_stats(mesh: pv.PolyData) -> dict:
    """Count boundary (hole) edges and non-manifold edges."""
    open_edges = mesh.extract_feature_edges(
        boundary_edges=True, non_manifold_edges=False,
        feature_edges=False, manifold_edges=False)
    nm_edges = mesh.extract_feature_edges(
        boundary_edges=False, non_manifold_edges=True,
        feature_edges=False, manifold_edges=False)
    return {"open_edges": int(open_edges.n_cells),
            "non_manifold_edges": int(nm_edges.n_cells)}


def remove_degenerate_and_duplicates(mesh: pv.PolyData) -> pv.PolyData:
    """Drop facets that collapse to a line/point and facets that appear twice."""
    faces = mesh.faces.reshape(-1, 4)[:, 1:]                 # VTK layout [3, a, b, c] -> [a, b, c]
    # degenerate: two or more identical vertex ids
    ok = (faces[:, 0] != faces[:, 1]) & (faces[:, 1] != faces[:, 2]) & (faces[:, 0] != faces[:, 2])
    faces = faces[ok]
    # zero-area facets
    p = mesh.points
    area2 = np.linalg.norm(np.cross(p[faces[:, 1]] - p[faces[:, 0]],
                                    p[faces[:, 2]] - p[faces[:, 0]]), axis=1)
    faces = faces[area2 > 1e-14 * max(area2.max(), 1.0)]
    # duplicate facets (same 3 vertices, any order)
    _, idx = np.unique(np.sort(faces, axis=1), axis=0, return_index=True)
    faces = faces[np.sort(idx)]
    out = pv.PolyData(p, np.hstack([np.full((len(faces), 1), 3), faces]).ravel())
    return out.clean(point_merging=False)


def estimate_reference(points, faces, h=0.002):
    """Rough reference values from a top-view (XY) occupancy grid, nose = +Y.

    area_m2   : projected planform area of the whole aircraft
    wing      : rows whose X-extent is >80% of the span are treated as the main wing
    length_m  : mean wing chord (wing area / span)
    moment_center_m : wing quarter-chord at the centreline, mid height
    These are estimates - replace them in config.json with your real numbers.
    """
    tri = points[faces][:, :, :2]                     # XY only
    a = 0.5 * np.abs(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]))
    n = np.ceil(a / (h * h) * 4).astype(int) + 3      # samples per triangle
    # scatter random points uniformly over every triangle (seeded: same answer every run)
    rng = np.random.default_rng(0)
    idx = np.repeat(np.arange(len(faces)), n)
    r1, r2 = rng.random(len(idx)), rng.random(len(idx))
    s = np.sqrt(r1)                                   # sqrt makes the barycentric sample uniform
    pts = ((1 - s)[:, None] * tri[idx, 0] + (s * (1 - r2))[:, None] * tri[idx, 1]
           + (s * r2)[:, None] * tri[idx, 2])
    # occupied h x h cells of the top view = planform
    lo = pts.min(axis=0)
    ij = np.unique(np.floor((pts - lo) / h).astype(np.int64), axis=0)
    area = len(ij) * h * h

    # group occupied cells into chordwise rows (constant y); rows spanning >80 % of the span = wing
    span = np.ptp(points[:, 0])
    rows = {}
    for i, j in ij:
        rows.setdefault(j, []).append(i)
    wing_rows = [j for j, ii in rows.items() if (max(ii) - min(ii) + 1) * h > 0.8 * span]
    wing_area = sum(len(rows[j]) for j in wing_rows) * h * h
    if wing_rows:
        y_le = lo[1] + (max(wing_rows) + 1) * h      # leading edge = most forward wing row
        y_te = lo[1] + min(wing_rows) * h
        chord = wing_area / span
        y_qc = y_le - 0.25 * chord                    # quarter chord, the usual moment reference
    else:
        chord, y_qc = area / span, float(points[:, 1].mean())
    z_mid = float(points[:, 2].mean())
    return {"planform_area_total_m2": area, "wing_area_est_m2": wing_area,
            "span_m": float(span), "mean_chord_est_m": float(chord),
            "moment_center_est_m": [0.0, float(y_qc), z_mid]}


def repair_local(m: pv.PolyData, passes: int = 5) -> pv.PolyData:
    """Cut out the triangles around open / non-manifold edges and re-fill the small holes.
    Ends with the largest closed shell (decimation can leave tiny detached slivers)."""
    for _ in range(passes):
        st = edge_stats(m)
        if not st["open_edges"] and not st["non_manifold_edges"]:
            break                                             # already clean
        bad = m.extract_feature_edges(boundary_edges=True, non_manifold_edges=True,
                                      feature_edges=False, manifold_edges=False)
        # every triangle touching a bad edge's vertices
        cells = set()
        for p in bad.points:
            cells.update(m.point_cell_ids(m.find_closest_point(p)))
        keep = np.setdiff1d(np.arange(m.n_cells), np.fromiter(cells, int))
        m = m.extract_cells(keep).extract_surface().clean()   # cut them out -> small clean holes
        m = m.fill_holes(0.02).triangulate().clean()          # re-fill holes up to 20 mm
        m = pv.PolyData(m.points, m.faces)
    return pv.PolyData(m.connectivity("largest").extract_surface().clean())


def shrink_wrap(mesh: pv.PolyData, h: float, target_facets: int = 300_000,
                close_gap: float = 0.0) -> pv.PolyData:
    """Rebuild the outer skin of a dirty assembly as ONE watertight, manifold surface.

    1. rasterise every facet into a voxel grid of spacing h (surface "shell")
    2. flood-fill the air from the grid boundary; everything the air can't reach
       is aircraft (this closes holes, overlaps and gaps smaller than ~h)
    3. build a signed distance field near the skin from the true facets, so the
       new surface sits within a fraction of h of the original one
    4. marching cubes -> keep the outer skin only -> light smoothing -> decimate
    """
    from scipy import ndimage
    from vtkmodules.util.numpy_support import numpy_to_vtk, vtk_to_numpy
    from vtkmodules.vtkFiltersCore import vtkImplicitPolyDataDistance

    pts = mesh.points.astype(np.float64)
    faces = mesh.faces.reshape(-1, 4)[:, 1:]
    # voxel grid = bounding box + a few empty layers of air all round
    pad = 4 + int(round(close_gap / (2 * h)))     # the sealing dilation must not touch the grid edge
    lo = pts.min(axis=0) - pad * h
    dims = np.ceil((pts.max(axis=0) + pad * h - lo) / h).astype(int) + 1
    print(f"  wrap: voxel {h*1000:.2f} mm, grid {dims.tolist()} = {np.prod(dims)/1e6:.0f}M voxels")

    # 1. shell voxels: sample each triangle densely enough to hit every voxel it crosses
    tri = pts[faces]
    area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    shell = np.zeros(dims, dtype=bool)
    rng = np.random.default_rng(0)
    for chunk in np.array_split(np.arange(len(faces)), 20):        # chunks keep the RAM in check
        n = np.ceil(area[chunk] / (h * h) * 8).astype(int) + 3     # ~8 samples per voxel of area
        idx = np.repeat(chunk, n)
        r1, r2 = rng.random(len(idx)), rng.random(len(idx))
        s = np.sqrt(r1)
        p = ((1 - s)[:, None] * tri[idx, 0] + (s * (1 - r2))[:, None] * tri[idx, 1]
             + (s * r2)[:, None] * tri[idx, 2])
        ijk = np.floor((p - lo) / h + 0.5).astype(int)
        shell[ijk[:, 0], ijk[:, 1], ijk[:, 2]] = True
    shell = ndimage.binary_dilation(shell, iterations=1)   # seal pin-holes between samples

    # 2. outside air = free voxels connected to the grid boundary.
    # With close_gap > 0, openings narrower than ~close_gap (hatch gaps, slots, a CAD skin with
    # holes) are sealed first: flood-fill around a shell thickened by k voxels, then grow that air
    # back by k voxels so it reaches the real skin again everywhere except inside the openings.
    k = int(round(close_gap / (2 * h)))
    sealed = ndimage.binary_dilation(shell, iterations=k) if k else shell
    labels, _ = ndimage.label(~sealed)            # connected pockets of free voxels
    outside = labels == labels[0, 0, 0]           # the pocket containing the grid corner = outside air
    del labels
    if k:
        outside = ndimage.binary_dilation(outside, iterations=k) & ~shell
        print(f"  wrap: sealing openings up to ~{close_gap*1000:.0f} mm ({k} voxels)")
    del sealed

    # 3. signed distance in a narrow band around the shell, from the real facets
    band = ndimage.binary_dilation(shell, iterations=2)
    # away from the skin phi is just +-3h (air / aircraft); exact distances only in the band
    phi = np.where(outside, 3.0 * h, -3.0 * h).astype(np.float32)
    bi = np.argwhere(band)
    q = lo + bi * h                               # band voxel centres in metres
    dist = vtkImplicitPolyDataDistance()          # distance from a point to the nearest original facet
    dist.SetInput(mesh)
    out = numpy_to_vtk(np.zeros(len(q)), deep=True)
    dist.FunctionValue(numpy_to_vtk(q, deep=True), out)
    d = vtk_to_numpy(out)
    # sign: outside air is +, anything the air can't reach is -; on the shell itself trust
    # the facet normals (they point out of each closed part in a CAD-exported STL)
    o, sh = outside[tuple(bi.T)], shell[tuple(bi.T)]
    signed = np.where(sh, d, np.where(o, np.abs(d), -np.abs(d)))
    # Only the OUTER skin matters. Facets of internal parts (servos, spars, inner faces of hollow
    # skins) more than 2 voxels from the outside air would otherwise leave near-touching internal
    # sheets in the iso-surface, which tear when decimated -> treat them as solid.
    near_air = ndimage.binary_dilation(outside, iterations=2)[tuple(bi.T)]
    signed = np.where(near_air, signed, -3 * h)
    phi[tuple(bi.T)] = np.clip(signed, -3 * h, 3 * h)
    del band, bi, q, d, o, sh, signed, near_air

    # 4. iso-surface, outer skin only, tidy up
    img = pv.ImageData(dimensions=dims, spacing=(h, h, h), origin=lo)
    img.point_data["phi"] = phi.ravel(order="F")                       # VTK is x-fastest (Fortran order)
    surf = img.contour([0.0], scalars="phi", method="flying_edges")    # the phi = 0 surface = new skin
    surf = surf.connectivity("largest").extract_surface().triangulate().clean()   # drop loose bits
    # Taubin smoothing removes the voxel stair-steps without shrinking the shape
    surf = surf.smooth_taubin(n_iter=20, pass_band=0.1).triangulate()
    surf = pv.PolyData(surf.points, surf.faces)          # polygons only (no stray lines/verts)
    print(f"  wrap: iso-surface {surf.n_cells} facets {edge_stats(surf)}")
    if surf.n_cells > target_facets:
        # Ansys Student refuses surfaces much above ~1M facets, so thin it out.
        # One big quadric step can tear thin parts (e.g. 2.4M -> 300k on the pod model), so
        # go down in steps of at most ~2.5x, repairing after each, and stop at the first clean result.
        st = None
        for max_ratio in (1e9, 2.5):
            dec = surf
            while dec.n_cells > target_facets * 1.05:
                goal = max(target_facets, dec.n_cells / max_ratio)
                dec = pv.PolyData(dec.decimate(1 - goal / dec.n_cells, volume_preservation=True).clean())
                dec = repair_local(pv.PolyData(dec.points, dec.faces), passes=15)
            st = edge_stats(dec)
            if st["open_edges"] == 0 and st["non_manifold_edges"] == 0:
                break
            print(f"  wrap: decimation in one step left {st}, retrying in smaller steps")
        if st["open_edges"] == 0 and st["non_manifold_edges"] == 0:
            surf = dec
            print(f"  wrap: decimated to {surf.n_cells} facets")
        else:
            print(f"  wrap: decimation broke the surface {st}, keeping full resolution "
                  f"(may exceed the Ansys Student limit - use a bigger --voxel-mm)")
    # consistent, outward-pointing normals (Fluent needs to know which side is the air)
    surf = surf.clean().compute_normals(cell_normals=True, point_normals=False,
                                        auto_orient_normals=True, consistent_normals=True)
    return surf


def write_binary_stl(path, points, faces, solid_name="aircraft"):
    """Binary STL with our own header: Fluent uses the header as the solid/zone name."""
    tri = points[faces].astype(np.float32)
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])           # facet normals
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-30)
    # STL record: normal (3 floats), 3 vertices (9 floats), 2-byte attribute
    rec = np.zeros(len(faces), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = n, tri
    with open(path, "wb") as fh:
        fh.write(solid_name.encode().ljust(80, b" "))   # 80-byte header
        fh.write(np.uint32(len(faces)).tobytes())       # facet count
        fh.write(rec.tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(DEFAULT_IN))
    ap.add_argument("--output", default=str(HERE / "aircraft_wrapped.stl"))
    ap.add_argument("--voxel-mm", type=float, default=1.5,
                    help="shrink-wrap resolution; smaller = more faithful but slower / more RAM")
    ap.add_argument("--close-mm", type=float, default=0.0,
                    help="seal openings/slots narrower than this (mm) so the wrap stays a solid "
                         "outer skin; needed when the CAD skin has hatch gaps (both cases use 24)")
    ap.add_argument("--units", choices=["auto", "mm", "m", "in"], default="auto",
                    help="units of the input STL (auto guesses from size)")
    ap.add_argument("--hole-size", type=float, default=0.0,
                    help="max hole size to fill, in output metres (0 = 2%% of span)")
    args = ap.parse_args()

    print(f"Reading {args.input}")
    mesh = pv.read(args.input).triangulate()              # quads (if any) -> triangles
    report = {"input": args.input, "input_facets": int(mesh.n_cells)}

    # ---- units ------------------------------------------------------------
    size = np.ptp(np.asarray(mesh.bounds).reshape(3, 2), axis=1)
    if args.units == "auto":
        # a small VTOL is 0.5-5 m across: >50 means mm, 20-50 probably inches
        units = "mm" if size.max() > 50 else ("in" if size.max() > 20 else "m")
    else:
        units = args.units
    scale = {"mm": 1e-3, "in": 0.0254, "m": 1.0}[units]
    mesh.points = mesh.points * scale
    report["units_assumed"] = units
    print(f"  {mesh.n_cells} facets, raw size {size.round(3)} -> assuming {units}")

    # ---- raw diagnostics --------------------------------------------------
    merged = mesh.clean(tolerance=1e-7, absolute=True)   # weld coincident vertices
    report["raw"] = edge_stats(merged)
    print(f"  raw: {report['raw']}")

    # ---- repair -----------------------------------------------------------
    m = remove_degenerate_and_duplicates(merged)
    span = float(np.ptp(np.asarray(m.bounds).reshape(3, 2), axis=1).max())
    hole = args.hole_size or 0.02 * span
    try:
        filled = m.fill_holes(hole)
        if filled.n_cells >= m.n_cells:
            m = filled
    except Exception as e:  # fill_holes can choke on very dirty input
        print(f"  hole filling skipped: {e}")
    m = m.clean().compute_normals(cell_normals=True, point_normals=False,
                                  consistent_normals=True, auto_orient_normals=False,
                                  non_manifold_traversal=False)

    # numbers for the report: separate bodies, remaining bad edges, size, reference estimates
    bodies = m.connectivity().cell_data["RegionId"]
    report["bodies"] = int(bodies.max() + 1) if len(bodies) else 0
    report["clean"] = edge_stats(m)
    report["clean_facets"] = int(m.n_cells)

    b = np.asarray(m.bounds).reshape(3, 2)
    report["bounds_m"] = b.tolist()
    report["size_m"] = np.ptp(b, axis=1).tolist()
    report["center_m"] = b.mean(axis=1).tolist()
    # smallest feature hint for meshing: median facet edge length
    f = m.faces.reshape(-1, 4)[:, 1:]
    e = np.linalg.norm(m.points[f[:, 1]] - m.points[f[:, 0]], axis=1)
    report["median_edge_m"] = float(np.median(e))
    report["reference"] = estimate_reference(m.points, f)
    print(f"  after facet repair: {report['clean']}, bodies: {report['bodies']}")

    # ---- shrink-wrap into one watertight skin -----------------------------
    # facet repair can't merge 59 overlapping parts; the wrap can.
    w = shrink_wrap(mesh, args.voxel_mm / 1000.0, close_gap=args.close_mm / 1000.0)
    wf = w.faces.reshape(-1, 4)[:, 1:]
    report["wrapped"] = {**edge_stats(w), "facets": int(w.n_cells),
                         "bodies": int(w.connectivity().cell_data["RegionId"].max() + 1),
                         "voxel_mm": args.voxel_mm}
    wb = np.asarray(w.bounds).reshape(3, 2)
    # how far the wrap moved the outline: a quick fidelity check (should be ~1-2 mm)
    report["wrapped"]["max_bbox_change_mm"] = float(np.abs(wb - b).max() * 1000)

    # Fluent Meshing reads STL as millimetres, so write mm (report stays in m)
    write_binary_stl(args.output, w.points * 1000.0, wf, solid_name="aircraft")
    report["output"] = args.output
    report["output_units"] = "mm"
    (HERE / "geometry_report.json").write_text(json.dumps(report, indent=2))

    print(f"  wrapped skin: {report['wrapped']}")
    print(f"  size (m): {np.round(report['size_m'], 4)}  center: {np.round(report['center_m'], 4)}")
    ref = report["reference"]
    print(f"  reference estimates: wing area {ref['wing_area_est_m2']:.4f} m2, "
          f"mean chord {ref['mean_chord_est_m']:.4f} m, span {ref['span_m']:.4f} m, "
          f"quarter-chord {np.round(ref['moment_center_est_m'], 4)}")
    print(f"Wrote {args.output} and geometry_report.json")
    rw = report["wrapped"]
    if rw["open_edges"] or rw["non_manifold_edges"] or rw["bodies"] != 1:
        print("WARNING: wrapped skin is not a single closed manifold - try a smaller --voxel-mm")


if __name__ == "__main__":
    main()
