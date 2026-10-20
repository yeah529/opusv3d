"""Characters rigged with Auto-Rig Pro (engine/arptool.py build): append the rig, pose it by steps, key the poses on
the timeline, hang props on bones. The film does not need the ARP add-on: the rig's drivers are plain expressions.

    R = rig.load(W, os.path.join(HERE, '02_assets/char_rig.blend'), 'hero', parent=root)      # rig + skinned mesh; feet at parent's origin
    IDLE = rig.pose(R, [('c_hand_ik.l', 'fk'), ('c_arm_fk.l', 'rot', 'Y', 65)])
    rig.act(R, [(0.0, IDLE), (1.2, CROUCH, 'out'), ...], extra=breath)     # one key per frame, rotations slerped
    grip = rig.socket(R, 'hand.r', M)          # an empty that follows the bone; M: its matrix in the rest pose

Steps work in the character's own space (rest pose: feet at the origin, face -Y, metres, degrees):
    (ctrl, 'fk') / (ctrl, 'ik')        limb switch, on c_hand_ik.* (arms) and c_foot_ik.* (legs)
    (ctrl, 'rot', axis, deg)           turn about a character axis (X, Y or Z) through the controller's head
    (ctrl, 'move', (dx, dy, dz))       move in character space
    (ctrl, 'to', M)                    put the controller at 4x4 matrix M (character space); a hand IK onto a prop
    (ctrl, 'prop', name, value)        a custom property, e.g. ('c_hand_ik.r', 'prop', 'auto_stretch', 1.0)
A '.l' step also does the mirrored '.r' unless the step ends with 'one' ('to' on a '.l' controller must end
with 'one': a matrix is not mirrored). Steps run in order: a later step starts
from where the earlier ones left the bones (turn the arm, then bend the forearm).
"""
import os

import bpy
from mathutils import Matrix, Quaternion, Vector

from . import anim, assets

SWITCH = 'ik_fk_switch'
MIRROR = {'X': 1, 'Y': -1, 'Z': -1}            # rotation sign of the .r copy (mirror across x = 0)


class Rig:
    def __init__(self, w, name, arm, meshes):
        self.w, self.name, self.arm, self.meshes = w, name, arm, meshes
        self.rest = None                       # {bone: {prop: value}} as loaded


def load(w, path, name, parent=None):
    """Append an arptool .blend into world w. Objects take the name prefix w.n(name); the top object is parented to
    `parent` with no offset, so the character's feet sit at the parent's origin."""
    if not os.path.exists(path):
        raise FileNotFoundError(f'rig: no file {path}')
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.objects = list(src.objects)
    objs = [o for o in dst.objects if o is not None]
    arms = [o for o in objs if o.type == 'ARMATURE']
    if len(arms) != 1:
        raise RuntimeError(f'rig: {path} has {len(arms)} armatures; expected one (build it with engine/arptool.py)')
    arm = arms[0]
    meshes = [o for o in objs if o.type == 'MESH' and any(m.type == 'ARMATURE' and m.object == arm for m in o.modifiers)]
    if not meshes:
        raise RuntimeError(f'rig: {path} has no mesh deformed by {arm.name}')
    missing = assets.missing_images(meshes)
    if missing:                            # else the character renders magenta, silently
        raise FileNotFoundError(f'rig: {path} uses texture(s) that are not there: {missing}. Paths are relative to the '
                                f'.blend: keep the texture folder next to it, as when it was built')
    keep = set(meshes) | {arm}
    for o in list(keep):
        p = o.parent
        while p is not None:
            keep.add(p)
            p = p.parent
    for o in objs:                         # the rest (ARP's controller shapes) stays unlinked: bones still draw them
        if o not in keep and o.users == 0:
            bpy.data.objects.remove(o)
    for o in keep:
        w.coll.objects.link(o)
        o.name = f'{w.n(name)}.{o.name}'
    arm.name = w.n(name)
    top = next(o for o in keep if o.parent is None)
    if parent is not None:
        top.parent, top.matrix_parent_inverse = parent, Matrix.Identity(4)
    R = Rig(w, name, arm, meshes)
    _update(R)
    return R


def _update(R):
    R.w.scene.view_layers[0].update()


def _props(pb):
    return {k: float(pb[k]) for k in pb.keys() if isinstance(pb[k], (int, float)) and not isinstance(pb[k], bool)}


_ARGS = {'fk': 2, 'ik': 2, 'rot': 4, 'move': 3, 'to': 3, 'prop': 4}   # items per step, without a trailing 'one'


def pose(R, steps):
    """Run steps from the rest pose; return {bone: (location, rotation quaternion, scale, {prop: value})} for the
    bones that left rest (props: only those the steps changed). The rig itself goes back to how it was."""
    arm = R.arm
    if R.rest is None:
        R.rest = {pb.name: _props(pb) for pb in arm.pose.bones}
    keep = {pb.name: (pb.matrix_basis.copy(), _props(pb)) for pb in arm.pose.bones}
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
        for k, v in R.rest[pb.name].items():
            pb[k] = v
    _update(R)
    for st in steps:
        if not isinstance(st, (tuple, list)) or len(st) < 2 or st[1] not in _ARGS:
            raise ValueError(f'rig.pose: bad step {st!r}; ops: {", ".join(_ARGS)}')
        if len(st) - (st[-1] == 'one') != _ARGS[st[1]]:
            raise ValueError(f'rig.pose: step {st!r} needs {_ARGS[st[1]]} items (ctrl, op, ...) plus an optional \'one\'')
        one = st[-1] == 'one'
        if st[1] == 'to' and st[0].endswith('.l') and not one:
            raise ValueError(f'rig.pose: {st[0]} "to" puts one controller on a matrix; end the step with \'one\' '
                             f'and give the .r side its own "to" step')
        names = [st[0]] if one or not st[0].endswith('.l') else [st[0], st[0][:-2] + '.r']
        for n in names:
            pb = arm.pose.bones.get(n)
            if pb is None:
                raise KeyError(f'rig.pose: no bone "{n}" in {arm.name}')
            op = st[1]
            if op in ('fk', 'ik'):
                if SWITCH not in pb.keys():
                    raise KeyError(f'rig.pose: {n} has no {SWITCH} (use c_hand_ik.* or c_foot_ik.*)')
                pb[SWITCH] = 1.0 if op == 'fk' else 0.0
            elif op == 'prop':
                if st[2] not in pb.keys():
                    raise KeyError(f'rig.pose: {n} has no property {st[2]!r}')
                pb[st[2]] = float(st[3])
            elif op == 'to':
                pb.matrix = Matrix(st[2])
            elif op == 'rot':
                if st[2] not in MIRROR:
                    raise ValueError(f'rig.pose: axis {st[2]!r}; use X, Y or Z')
                ang = st[3] * (MIRROR[st[2]] if n.endswith('.r') and n != st[0] else 1)
                M = pb.matrix.copy()
                h = M.translation.copy()
                pb.matrix = Matrix.Translation(h) @ Matrix.Rotation(ang * 3.141592653589793 / 180, 4, st[2]) @ Matrix.Translation(-h) @ M
            elif op == 'move':
                d = Vector(st[2])
                if n.endswith('.r') and n != st[0]:
                    d.x = -d.x
                M = pb.matrix.copy()
                M.translation += d
                pb.matrix = M
            else:
                raise ValueError(f'rig.pose: unknown step {st!r}')
            _update(R)
    out = {}
    for pb in arm.pose.bones:
        pr = {k: v for k, v in _props(pb).items() if v != R.rest[pb.name].get(k)}
        moved = any(abs(a - b) > 1e-6 for r1, r2 in zip(pb.matrix_basis, Matrix.Identity(4)) for a, b in zip(r1, r2))
        if moved or pr:
            loc, q, s = pb.matrix_basis.decompose()
            out[pb.name] = (loc, q, s, pr)
    for pb in arm.pose.bones:
        pb.matrix_basis = keep[pb.name][0]
        for k, v in keep[pb.name][1].items():
            pb[k] = v
    _update(R)
    return out


def blend(R, a, b, x):
    """A pose part way (x 0..1; an overshooting ease may go past 1) from pose a to pose b."""
    out = {}
    for n in set(a) | set(b):
        la, qa, sa, pa = a.get(n, _REST)
        lb, qb, sb, pbp = b.get(n, _REST)
        if qa.dot(qb) < 0:
            qb = -qb
        rest = R.rest[n]
        pr = {k: pa.get(k, rest[k]) + (pbp.get(k, rest[k]) - pa.get(k, rest[k])) * x for k in set(pa) | set(pbp)}
        d = qa.rotation_difference(qb)                 # qa @ d == qb; scaling its angle allows x outside 0..1 (overshoot)
        out[n] = (la.lerp(lb, x), qa @ Quaternion(d.axis, d.angle * x), sa.lerp(sb, x), pr)
    return out


_REST = (Vector(), Quaternion(), Vector((1, 1, 1)), {})


def act(R, keys, extra=None):
    """Key poses [(t, pose) or (t, pose, ease into it)], one key per frame from the first time to the last; a bone a
    pose leaves out is at rest in that pose. extra(t) -> {bone: Quaternion} turns bones on top (breathing, a head
    bob), in the bone's own axes. Later act() calls replace earlier keys inside their time range."""
    keys = sorted(keys, key=lambda k: k[0])
    if not keys:
        return
    for k in keys:
        if not isinstance(k[1], dict):
            raise TypeError(f'rig.act: key at t={k[0]} holds {type(k[1]).__name__}; give it a pose from rig.pose(R, steps)')
    t0, t1 = keys[0][0], keys[-1][0]
    names = set().union(*(k[1] for k in keys)) | set(extra(t0) if extra else ())
    for n in names:
        if n not in R.arm.pose.bones:
            raise KeyError(f'rig.act: no bone "{n}" in {R.arm.name}')
        R.arm.pose.bones[n].rotation_mode = 'QUATERNION'
    frames = range(anim.F(t0), anim.F(t1) + 1)
    vals = {}
    for f in frames:
        t = t1 if f == frames[-1] else t0 if f == frames[0] else f / anim.FPS   # end frames exactly on the end poses
        j = 0
        while j < len(keys) - 2 and t > keys[j + 1][0]:
            j += 1
        a, b = keys[j], keys[min(j + 1, len(keys) - 1)]
        x = 1.0 if b[0] <= a[0] else anim.ease(b[2] if len(b) > 2 else 'inout', (t - a[0]) / (b[0] - a[0]))
        p = blend(R, a[1], b[1], x)
        add = extra(t) if extra else {}
        for n in names:
            loc, q, s, pr = p.get(n, _REST)
            if n in add:
                q = q @ add[n]
            vals.setdefault(n, []).append((f, loc, q, s, pr))
    for n, rows in vals.items():
        base = f'pose.bones["{n}"]'
        prev = None
        for i, (f, loc, q, s, sw) in enumerate(rows):          # keep neighbouring quaternions on one hemisphere
            if prev is not None and prev.dot(q) < 0:
                rows[i] = (f, loc, -q, s, sw)
            prev = rows[i][2]
        for k in range(3):
            anim._write(R.arm, base + '.location', k, [(r[0], r[1][k]) for r in rows])
            anim._write(R.arm, base + '.scale', k, [(r[0], r[3][k]) for r in rows])
        for k in range(4):
            anim._write(R.arm, base + '.rotation_quaternion', k, [(r[0], r[2][k]) for r in rows])
        for k in sorted(set().union(*(r[4] for r in rows))):    # a prop any key changes: keyed on every frame
            rest = R.rest[n][k]
            anim._write(R.arm, f'{base}["{k}"]', 0, [(r[0], r[4].get(k, rest)) for r in rows])


def socket(R, bone, M, name=None):
    """An empty that follows `bone`. M (4x4, character space) is where the empty sits while the rig is in its rest
    pose. Give a prop a Copy Transforms on it, or parent the prop to it."""
    b = R.arm.data.bones.get(bone)
    if b is None:
        raise KeyError(f'rig.socket: no bone "{bone}" in {R.arm.name}')
    e = R.w.empty(f'{R.name}.{name or bone}')
    c = e.constraints.new('CHILD_OF')
    c.target, c.subtarget = R.arm, bone
    c.inverse_matrix = Matrix.Identity(4)
    e.matrix_basis = b.matrix_local.inverted() @ Matrix(M)
    return e
