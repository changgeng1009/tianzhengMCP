import json, math

def solve_2point_affine(ref_pts, tgt_pts):
    if len(ref_pts) < 2 or len(tgt_pts) < 2: return None
    r0, r1 = ref_pts[0], ref_pts[1]
    t0, t1 = tgt_pts[0], tgt_pts[1]
    dx_r = r1[0]-r0[0]; dy_r = r1[1]-r0[1]
    dx_t = t1[0]-t0[0]; dy_t = t1[1]-t0[1]
    if dx_r == 0 and dy_r == 0: return None
    sx = math.hypot(dx_t, dy_t) / math.hypot(dx_r, dy_r)
    sy = sx
    ang_r = math.atan2(dy_r, dx_r); ang_t = math.atan2(dy_t, dx_t)
    rot = math.degrees(ang_t - ang_r)
    ox = t0[0] - sx*(math.cos(math.radians(rot))*r0[0] - math.sin(math.radians(rot))*r0[1])
    oy = t0[1] - sx*(math.sin(math.radians(rot))*r0[0] + math.cos(math.radians(rot))*r0[1])
    errs = []
    for rp, tp in zip(ref_pts, tgt_pts):
        rx = sx*(math.cos(math.radians(rot))*rp[0]-math.sin(math.radians(rot))*rp[1])+ox
        ry = sx*(math.sin(math.radians(rot))*rp[0]+math.cos(math.radians(rot))*rp[1])+oy
        errs.append(math.hypot(rx-tp[0], ry-tp[1]))
    rms = math.sqrt(sum(e*e for e in errs)/len(errs))
    max_err = max(errs)
    conf = max(0.0, min(1.0, 1.0 - rms / (max(abs(sx*dx_r), abs(sy*dy_r), 1))))
    return {'transform_type':'2point_similarity','scale_x':sx,'scale_y':sy,'rotation_deg':rot,
        'translation':[ox,oy],'rms_error':rms,'max_error':max_err,'confidence':conf,
        'hardcoded_extent_used':False,'source_dwg_opened':False,'sendcommand_used':False}

def solve_3point_affine(ref_pts, tgt_pts):
    if len(ref_pts) < 3 or len(tgt_pts) < 3: return None
    r0,r1,r2 = ref_pts[:3]; t0,t1,t2 = tgt_pts[:3]
    # Affine: [sx*cos -sx*sin ox; sy*sin sy*cos oy]
    # Solve 6-param via least squares
    A = []; B = []
    for (rx,ry),(tx,ty) in zip(ref_pts[:3], tgt_pts[:3]):
        A.append([rx,-ry,1,0,0,0]); A.append([ry,rx,0,1,0,0])
        B.append(tx); B.append(ty)
    for i in range(len(A)):
        for j in range(3,6): A[i].append(0)
    # Simple 3-point exact solve
    det = (r0[0]-r1[0])*(r0[1]-r2[1]) - (r0[0]-r2[0])*(r0[1]-r1[1])
    if abs(det) < 0.001: return solve_2point_affine(ref_pts[:2], tgt_pts[:2])
    sx = ((t0[0]-t1[0])*(r0[1]-r2[1]) - (t0[0]-t2[0])*(r0[1]-r1[1])) / det
    sy = ((r0[0]-r1[0])*(t0[1]-t2[1]) - (r0[0]-r2[0])*(t0[1]-t1[1])) / det
    ox = t0[0]-sx*r0[0]; oy = t0[1]-sy*r0[1]
    rot = math.degrees(math.atan2(sy-sx, sx+sy)) if abs(sx+sy)>1e-10 else 0
    errs = []
    for rp, tp in zip(ref_pts, tgt_pts):
        tx_c = sx*rp[0]+ox; ty_c = sy*rp[1]+oy
        errs.append(math.hypot(tx_c-tp[0], ty_c-tp[1]))
    rms = math.sqrt(sum(e*e for e in errs)/len(errs))
    conf = max(0.0, min(1.0, 1.0-rms/max(abs(sx*1000),abs(sy*1000),1)))
    return {'transform_type':'3point_affine','scale_x':sx,'scale_y':sy,'rotation_deg':rot,
        'translation':[ox,oy],'rms_error':rms,'max_error':max(errs),
        'confidence':conf,'hardcoded_extent_used':False,'source_dwg_opened':False,'sendcommand_used':False}

def calibrate(ref_anchors, sbx_anchors):
    if len(ref_anchors) >= 3:
        return solve_3point_affine(ref_anchors, sbx_anchors)
    elif len(ref_anchors) >= 2:
        return solve_2point_affine(ref_anchors, sbx_anchors)
    return None
