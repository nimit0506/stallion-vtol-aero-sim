"""
Test: is the wrapped skin a SOLID outer surface? Shoots vertical rays through the fuselage and pod
and reports air pockets enclosed by the skin (hollow interior = the wrap leaked inside the CAD shell).

  ..\\.venv\\Scripts\\python.exe check_solid.py [aircraft_wrapped.stl]
"""
import sys

import numpy as np
import pyvista as pv

path = sys.argv[1] if len(sys.argv) > 1 else "aircraft_wrapped.stl"
m = pv.read(path)
m.points = m.points / 1000.0                     # STL is mm
inner = []                                       # (x, y, z where the air starts mm, air length mm)
# a 5 x 16 grid of vertical rays: x across the fuselage width, y from the nose back to the wing
for x in np.arange(-0.04, 0.041, 0.02):
    for y in np.arange(0.03, -0.45, -0.03):
        pts, _ = m.ray_trace((x, y, -0.3), (x, y, 0.4))   # every skin crossing along the ray
        z = np.sort(pts[:, 2]) if len(pts) else np.array([])
        # hits alternate enter/exit; air between an exit and the next entry
        for i in range(1, len(z) - 1, 2):
            gap = z[i + 1] - z[i]
            # only air INSIDE the fuselage body (its underside is at z>~0); air between the
            # fuselage and the pod below it is the real outside flow (notches at the pod ends)
            if gap > 0.003 and z[i] > 0.005:
                inner.append((round(x, 3), round(y, 3), round(z[i] * 1000, 1), round(gap * 1000, 1)))
# gaps under 15 mm are thin seams the mesher handles; bigger ones mean a hollow body (huge mesh)
big = [g for g in inner if g[3] > 15]
print(f"rays: {5 * 16}, enclosed air gaps >3 mm: {len(inner)}, >15 mm: {len(big)}")
for g in big[:15]:
    print(f"  x={g[0]} y={g[1]} from z={g[2]} mm, {g[3]} mm of air")
print("SOLID" if not big else "HOLLOW - raise --close-mm")
sys.exit(1 if big else 0)                        # stops run_all.bat on a hollow wrap
