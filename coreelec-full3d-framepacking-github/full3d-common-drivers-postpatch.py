#!/usr/bin/env python3
import sys
import re
from pathlib import Path

MARK = "FULL3D_FP_V030RC1"
OLD_MARKS = ("FULL3D_FP_V0233STOCKPREBLENDH", "FULL3D_FP_V0232NOSYNTHVD2SCBLGATE", "FULL3D_FP_V0231NOSYNTHVD2POSGATE", "FULL3D_FP_V0230NOSYNTHPATHSEL", "FULL3D_FP_V0229VD2CANVAS0ONLY", "FULL3D_FP_V0226SINGLEVD2ENABLE", "FULL3D_FP_V0224NOGENPARITY", "FULL3D_FP_V0222MVCGEN2RESET", "FULL3D_FP_V0221MVCSAFE", "FULL3D_FP_V0220CLEAN", "FULL3D_FP_V0219", "FULL3D_FP_V0217", "FULL3D_FP_V0216", "FULL3D_FP_V0214", "FULL3D_FP_V0213", "FULL3D_FP_V0211", "FULL3D_FP_V0210", "FULL3D_FP_V029", "FULL3D_FP_V028", "FULL3D_FP_V027")

if len(sys.argv) != 2:
    raise SystemExit("usage: full3d-common-drivers-postpatch.py <PKG_BUILD>")

root = Path(sys.argv[1])
video_hw = root / "drivers/media/video_sink/video_hw.c"
video_func = root / "drivers/media/video_sink/video_func.c"
for expected in (video_hw, video_func):
    if not expected.is_file():
        raise SystemExit(f"ERROR: expected source file not found: {expected}")


def function_slice(text: str, start_token: str):
    """Return one complete C function using brace matching."""
    start = text.find(start_token)
    if start < 0:
        raise SystemExit(f"ERROR: function start not found: {start_token}")

    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit(f"ERROR: opening brace not found: {start_token}")

    depth = 0
    i = brace
    state = "code"
    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""

        if state == "code":
            if c == "/" and n == "*":
                state = "block_comment"
                i += 2
                continue
            if c == "/" and n == "/":
                state = "line_comment"
                i += 2
                continue
            if c == '"':
                state = "string"
                i += 1
                continue
            if c == "'":
                state = "char"
                i += 1
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    if end < len(text) and text[end] == "\n":
                        end += 1
                    return start, end, text[start:end]
            i += 1
            continue

        if state == "block_comment":
            if c == "*" and n == "/":
                state = "code"
                i += 2
            else:
                i += 1
            continue

        if state == "line_comment":
            if c == "\n":
                state = "code"
            i += 1
            continue

        if state in ("string", "char"):
            quote = '"' if state == "string" else "'"
            if c == "\\":
                i += 2
                continue
            if c == quote:
                state = "code"
            i += 1
            continue

    raise SystemExit(f"ERROR: closing brace not found: {start_token}")


htxt = video_hw.read_text()

if MARK in htxt:
    print("FULL3D: common_drivers post-patch already present (v0.3.0-rc1)")
    raise SystemExit(0)

if any(old in htxt for old in OLD_MARKS):
    raise SystemExit(
        "ERROR: older FULL3D modifications are already present in this unpacked common_drivers tree. "
        "Run './scripts/clean common_drivers' and unpack again before applying v0.3.0-rc1."
    )

# v0.2.14 deliberately leaves vpp_get_video_source_size() untouched.
# MODE_FORCE_3D_LR/TB already gives the desired virtual source geometry:
#   3840x1080 SBS -> 1920x2160
#   1920x2160 TAB -> 1920x2160
# The HDMI 45-line blank belongs to OUTPUT geometry, not decoded source geometry.


# 0) Keep common_drivers' internal frame-packing state in sync with the
# synthetic Full-SBS/TAB HDMI mode.  hdmitx already enters 3dfp, but the
# stock function only marks decoded MVC (or TV-input FP) as frame-packed.
# Without this, lower-level VD/MIF programming still follows the non-FP path.
start, end, fn = function_slice(htxt, "static void is_framepacking_support")
anchor = "	if (vf->type & VIDTYPE_MVC) {\n		framepacking_support = g_framepacking_support;\n	} else {\n"
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: is_framepacking_support anchor mismatch: found {fn.count(anchor)}")
replacement = f"""	if ((process_3d_type & MODE_3D_FP) &&
	    !(vf->type & VIDTYPE_MVC)) {{
		/* {MARK}: synthetic SBS/TB frame packing must not depend on the
		 * MVC module parameter, which CoreELEC resets to 0 on stop. */
		framepacking_support = 1;
	}} else if (vf->type & VIDTYPE_MVC) {{
		framepacking_support = g_framepacking_support;
	}} else {{
"""
fn = fn.replace(anchor, replacement, 1)
htxt = htxt[:start] + fn + htxt[end:]

# 1) Source-eye vertical coordinates. Use the decoded visible geometry rather
# than the virtual frame-packed output geometry.
start, end, fn = function_slice(htxt, "static void get_3d_vert_pos")
anchor = "\tif (vpp_3d_mode == VPP_3D_MODE_TB) {\n"
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: get_3d_vert_pos anchor mismatch: found {fn.count(anchor)}")
block = f"""\t/* {MARK}: synthetic FP reads eye coordinates from the decoded SBS/TB source. */
\tif ((process_3d_type & MODE_3D_FP) &&
\t    !(vf->type & VIDTYPE_MVC)) {{
\t\tu32 visible_height = vf->height;

\t\tif (vpp_3d_mode == VPP_3D_MODE_LR) {{
\t\t\t*ls = crop_sy;
\t\t\t*le = visible_height - crop_ey - 1;
\t\t\t*rs = *ls;
\t\t\t*re = *le;
\t\t}} else if (vpp_3d_mode == VPP_3D_MODE_TB) {{
\t\t\tu32 eye_height = visible_height >> 1;

\t\t\t*ls = crop_sy;
\t\t\t*le = eye_height - crop_ey - 1;
\t\t\t*rs = eye_height + crop_sy;
\t\t\t*re = visible_height - crop_ey - 1;
\t\t}} else {{
\t\t\t*ls = *rs = layer->start_y_lines;
\t\t\t*le = *re = layer->end_y_lines;
\t\t}}
\t\tif (vf->type & VIDTYPE_INTERLACE) {{
\t\t\t*ls >>= 1;
\t\t\t*le >>= 1;
\t\t\t*rs >>= 1;
\t\t\t*re >>= 1;
\t\t}}
\t\treturn;
\t}}
\tif (vpp_3d_mode == VPP_3D_MODE_TB) {{
"""
fn = fn.replace(anchor, block, 1)
htxt = htxt[:start] + fn + htxt[end:]

# 2) VD2 must read the right eye. MVC only needs a vertical swap because its
# eyes are separate surfaces; SBS additionally needs the right horizontal half.
start, end, fn = function_slice(htxt, "void config_3d_vd2_position")
anchor = "\tif ((dispbuf->type & VIDTYPE_MVC) && framepacking_support) {\n"
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: config_3d_vd2_position anchor mismatch: found {fn.count(anchor)}")
block = f"""\t/* {MARK}: feed synthetic VD2 from the calculated right-eye MIF rectangle.
\t * The proven Full3D path is ordinary uncompressed MIF. */
\tif ((process_3d_type & MODE_3D_FP) &&
\t    !(dispbuf->type & VIDTYPE_MVC)) {{
\t\tsetting->l_hs_chrm = setting->r_hs_chrm;
\t\tsetting->l_he_chrm = setting->r_he_chrm;
\t\tsetting->l_hs_luma = setting->r_hs_luma;
\t\tsetting->l_he_luma = setting->r_he_luma;
\t\tsetting->l_vs_chrm = setting->r_vs_chrm;
\t\tsetting->l_ve_chrm = setting->r_ve_chrm;
\t\tsetting->l_vs_luma = setting->r_vs_luma;
\t\tsetting->l_ve_luma = setting->r_ve_luma;
\t\tsetting->r_hs_luma = 0;
\t\tsetting->r_he_luma = 0;
\t\tsetting->r_hs_chrm = 0;
\t\tsetting->r_he_chrm = 0;
\t\tsetting->r_vs_luma = 0;
\t\tsetting->r_ve_luma = 0;
\t\tsetting->r_vs_chrm = 0;
\t\tsetting->r_ve_chrm = 0;
\t}} else if ((dispbuf->type & VIDTYPE_MVC) && framepacking_support) {{
"""
fn = fn.replace(anchor, block, 1)
htxt = htxt[:start] + fn + htxt[end:]

# 3) Keep the HDMI blank out of the DECODED source dimensions.
start, end, fn = function_slice(htxt, "s32 config_vd_position_internal")
anchor = "\tif (framepacking_support)\n\t\tblank = framepacking_blank;\n\telse\n\t\tblank = 0;\n\tsetting->src_h -= blank;\n"
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: config_vd_position_internal blank anchor mismatch: found {fn.count(anchor)}")
replacement = f"""\t/* {MARK}: the 45-line FP blank is output timing, not part of an SBS/TB decode buffer. */
\tif ((process_3d_type & MODE_3D_FP) &&
\t    !(dispbuf->type & VIDTYPE_MVC))
\t\tblank = 0;
\telse if (framepacking_support)
\t\tblank = framepacking_blank;
\telse
\t\tblank = 0;
\tsetting->src_h -= blank;
"""
fn = fn.replace(anchor, replacement, 1)
htxt = htxt[:start] + fn + htxt[end:]

# 4) Synthetic frame packing uses a 2160-line *virtual VPP canvas* containing
# two 1080-line eyes back-to-back. The HDMI transmitter inserts the 45-line
# frame-packing blank later; therefore the blank must NOT be subtracted here.
# Keep the stock MVC branch untouched because true MVC frames may already carry
# frame-packing geometry via framepacking_support.
start, end, fn = function_slice(htxt, "static void config_vd_param_internal")
old = """\t} else if ((dispbuf->type & VIDTYPE_MVC) &&
\t    !is_enable_3d_to_2d()) {
\t\t/* mvc case, (height - blank)/2 */
\t\tif (framepacking_support)
\t\t\tblank = framepacking_blank;
\t\telse
\t\t\tblank = 0;
\t\tzoom_start_y /= 2;
\t\tzoom_end_y = ((zoom_end_y - blank + 1) >> 1) - 1;
\t}
"""
if fn.count(old) != 1:
    raise SystemExit(f"ERROR: config_vd_param_internal MVC anchor mismatch: found {fn.count(old)}")
new = f"""\t}} else if ((process_3d_type & MODE_3D_FP) &&
\t\t   !(dispbuf->type & VIDTYPE_MVC) &&
\t\t   !is_enable_3d_to_2d()) {{
\t\t/* {MARK}: split the virtual 2160-line VPP canvas evenly: 1080 + 1080. */
\t\tzoom_start_y /= 2;
\t\tzoom_end_y = ((zoom_end_y + 1) >> 1) - 1;
\t}} else if ((dispbuf->type & VIDTYPE_MVC) &&
\t    !is_enable_3d_to_2d()) {{
\t\t/* mvc case, (height - blank)/2 */
\t\tif (framepacking_support)
\t\t\tblank = framepacking_blank;
\t\telse
\t\t\tblank = 0;
\t\tzoom_start_y /= 2;
\t\tzoom_end_y = ((zoom_end_y - blank + 1) >> 1) - 1;
\t}}
"""
fn = fn.replace(old, new, 1)
htxt = htxt[:start] + fn + htxt[end:]

# 5) Match the proven-good MVC output raster.  The physical 1080p FP raster is
# 1080 left + 45 blank + 1080 right = 2205 lines.  v0.2.16 placed VD2 at
# 1080..2159; the MVC register dump proves the correct right-eye interval is
# 1125..2204.  Keep decoded/source geometry at 1080 lines per eye.
start, end, fn = function_slice(htxt, "s32 config_3d_vd2_blend")
anchor = "\t} else if (dispbuf && (dispbuf->type & VIDTYPE_MVC)) {\n"
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: config_3d_vd2_blend MVC anchor mismatch: found {fn.count(anchor)}")
block = f"""	}} else if ((process_3d_type & MODE_3D_FP) &&
		   dispbuf && !(dispbuf->type & VIDTYPE_MVC)) {{
		u32 blank;

		/* {MARK}: synthetic packed sources keep VPP_vd_* at the
		 * 2160-line virtual source canvas, while VPP_vsc_* describes
		 * the actual 2205-line frame-packed output window.  Place VD2
		 * from the OUTPUT window, matching real MVC exactly. */
		if (framepacking_support)
			blank = framepacking_blank;
		else
			blank = 0;
		setting->postblend_v_start =
			cur_frame_par->VPP_vsc_startp +
			(((cur_frame_par->VPP_vsc_endp -
			   cur_frame_par->VPP_vsc_startp + 1 - blank) >> 1) + blank);
		setting->postblend_v_end = cur_frame_par->VPP_vsc_endp;
		setting->postblend_h_start = cur_frame_par->VPP_hsc_startp;
		setting->postblend_h_end = cur_frame_par->VPP_hsc_endp;
	}} else if (dispbuf && (dispbuf->type & VIDTYPE_MVC)) {{
"""
fn = fn.replace(anchor, block, 1)
htxt = htxt[:start] + fn + htxt[end:]


# 5b) The real MVC path programs the logical VPP picture/preblend canvas as
# 1920x2205 even though each eye MIF still reads only 1920x1080 (2160 eye
# lines total).  Synthetic FP was still advertising 2160 here, which clips
# the final 45 lines of VD2 after the correctly positioned 1125..2204 blend.
# Do NOT change decoded/MIF source geometry; only extend the logical VPP
# canvas to the actual frame-packed output height.
start, end, fn = function_slice(htxt, "static void vd1_scaler_setting")
anchor = """\t/*vpp input size setting*/
\tcur_dev->rdma_func[vpp_index].rdma_wr
\t\t(VPP_IN_H_V_SIZE + misc_off,
\t\t((frame_par->video_input_w & 0x1fff) << 16)
\t\t| (frame_par->video_input_h & 0x1fff));

\tcur_dev->rdma_func[vpp_index].rdma_wr
\t\t(VPP_PIC_IN_HEIGHT + misc_off,
\t\tframe_par->VPP_pic_in_height_);
"""
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: vd1_scaler_setting VPP input-size anchor mismatch: found {fn.count(anchor)}")
replacement = f"""\t/*vpp input size setting*/
\t{{
\t\tu32 full3d_vpp_h = frame_par->video_input_h;

\t\tif ((process_3d_type & MODE_3D_FP) && framepacking_support &&
\t\t    layer->dispbuf && !(layer->dispbuf->type & VIDTYPE_MVC)) {{
\t\t\t/* {MARK}: logical FP canvas = 1080 + blank + 1080. */
\t\t\tfull3d_vpp_h = frame_par->VPP_vsc_endp -
\t\t\t\tframe_par->VPP_vsc_startp + 1;
\t\t}}
\t\tcur_dev->rdma_func[vpp_index].rdma_wr
\t\t\t(VPP_IN_H_V_SIZE + misc_off,
\t\t\t((frame_par->video_input_w & 0x1fff) << 16)
\t\t\t| (full3d_vpp_h & 0x1fff));
\t\tcur_dev->rdma_func[vpp_index].rdma_wr
\t\t\t(VPP_PIC_IN_HEIGHT + misc_off, full3d_vpp_h);
\t}}
"""
fn = fn.replace(anchor, replacement, 1)
htxt = htxt[:start] + fn + htxt[end:]

start, end, fn = function_slice(htxt, "s32 config_vd_blend")
# CoreELEC's patch stack can reformat this block, so anchor semantically on the
# temp_h initialization rather than the whole surrounding if-block.
pat = re.compile(
    r"(?m)^(?P<indent>[ \t]*)(?P<decl>u32[ \t]+)?temp_h[ \t]*=[ \t]*"
    r"cur_frame_par->video_input_h[ \t]*;[ \t]*$"
)
matches = list(pat.finditer(fn))
if len(matches) != 1:
    raise SystemExit(
        f"ERROR: config_vd_blend temp_h semantic anchor mismatch: found {len(matches)}"
    )
m = matches[0]
indent = m.group("indent")
decl = m.group("decl") or ""
replacement = (
    f"{indent}{decl}temp_h = cur_frame_par->video_input_h;\n"
    f"{indent}if ((process_3d_type & MODE_3D_FP) && framepacking_support &&\n"
    f"{indent}    dispbuf && !(dispbuf->type & VIDTYPE_MVC)) {{\n"
    f"{indent}\t/* {MARK}: preblend must span the full 2205-line FP canvas. */\n"
    f"{indent}\ttemp_h = cur_frame_par->VPP_vsc_endp -\n"
    f"{indent}\t\tcur_frame_par->VPP_vsc_startp + 1;\n"
    f"{indent}}}"
)
fn = fn[:m.start()] + replacement + fn[m.end():]
htxt = htxt[:start] + fn + htxt[end:]

# 6) Synthetic FP is not VIDTYPE_MVC, so stock layer_swap_frame() never powers
# VD2 merely because MODE_3D_FP is active. Explicitly enable VD2 for the
# synthetic two-eye path, without pretending the decoded frame is MVC (MVC has
# a different second-surface/canvas model).
start, end, fn = function_slice(htxt, "s32 layer_swap_frame")
anchor = "\tbool is_mvc = false;\n"
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: layer_swap_frame local anchor mismatch: found {fn.count(anchor)}")
fn = fn.replace(anchor, anchor + "\tbool synthetic_fp = false;\n", 1)

anchor = "\tlayer_info = &glayer_info[layer_id];\n"
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: layer_swap_frame init anchor mismatch: found {fn.count(anchor)}")
replacement = f"""\tlayer_info = &glayer_info[layer_id];
\tsynthetic_fp = (layer_id == 0) &&
\t\t(process_3d_type & MODE_3D_FP) &&
\t\t!(vf->type & VIDTYPE_MVC) &&
\t\t!is_enable_3d_to_2d();
"""
fn = fn.replace(anchor, replacement, 1)

# The later fallback immediately below is sufficient to enable VD2 whenever
# VD1 is active for synthetic FP. Keep the first-picture/enable_layer branch
# stock (layer_id == 1 || is_mvc) so synthetic FP has only one explicit VD2
# power-on extension.
pat = re.compile(r"(?m)^(?P<i>[ \t]*)if \(layer_id == 1 \|\| is_mvc\)\n(?P=i)\tenable_video_layer2\(\);")
matches = list(pat.finditer(fn))
if len(matches) != 1:
    raise SystemExit(f"ERROR: layer_swap_frame stock enable anchor mismatch: found {len(matches)}")

pat = re.compile(r"(?m)^(?P<i>[ \t]*)if \(vd_layer\[0\]\.enabled && !vd_layer\[1\]\.enabled &&\n(?P=i)\t\(is_mvc \|\| video_lcevc\.vd2_vd1_shared_vf\)\)\n(?P=i)\tenable_video_layer2\(\);")
matches = list(pat.finditer(fn))
if len(matches) != 1:
    raise SystemExit(f"ERROR: layer_swap_frame fallback enable anchor mismatch: found {len(matches)}")
fn = pat.sub(lambda m: f"{m.group('i')}if (vd_layer[0].enabled && !vd_layer[1].enabled &&\n{m.group('i')}\t(is_mvc || synthetic_fp || video_lcevc.vd2_vd1_shared_vf))\n{m.group('i')}\tenable_video_layer2();", fn, count=1)
htxt = htxt[:start] + fn + htxt[end:]

# 7) Synthetic VD2 must follow the SAME current packed decode canvas as VD1.
# Stock set_layer_display_canvas() refreshes the second MIF canvas only for MVC,
# where the decoder supplies a separate right-eye surface.  Synthetic SBS/TAB
# instead needs the current VD1 surface on VD2 plus the independent right-eye crop.
start, end, fn = function_slice(htxt, "int set_layer_display_canvas")
anchor = "\tbool is_mvc = false;\n"
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: set_layer_display_canvas local anchor mismatch: found {fn.count(anchor)}")
fn = fn.replace(anchor, anchor + "\tbool synthetic_fp = false;\n", 1)
anchor = "\tif ((vf->type & VIDTYPE_MVC) && layer_id == 0)\n\t\tis_mvc = true;\n"
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: set_layer_display_canvas MVC anchor mismatch: found {fn.count(anchor)}")
fn = fn.replace(anchor, anchor +
    "\tsynthetic_fp = (layer_id == 0) &&\n"
    "\t\t(process_3d_type & MODE_3D_FP) && !is_mvc;\n", 1)
anchor = """\t\tif (is_mvc)
\t\t\tcur_dev->rdma_func[vpp_index].rdma_wr
\t\t\t\t(vd_mif_reg_mvc->vd_if0_canvas0,
\t\t\t\tlayer->disp_canvas[cur_canvas_id][1]);
"""
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: set_layer_display_canvas canvas0 anchor mismatch: found {fn.count(anchor)}")
replacement = f"""\t\tif (is_mvc)
\t\t\tcur_dev->rdma_func[vpp_index].rdma_wr
\t\t\t\t(vd_mif_reg_mvc->vd_if0_canvas0,
\t\t\t\tlayer->disp_canvas[cur_canvas_id][1]);
\t\telse if (synthetic_fp) {{
\t\t\t/* {MARK}: both synthetic eyes live in one packed surface. */
\t\t\tcur_dev->rdma_func[vpp_index].rdma_wr
\t\t\t\t(vd_mif_reg_mvc->vd_if0_canvas0,
\t\t\t\tlayer->disp_canvas[cur_canvas_id][0]);
\t\t}}
"""
fn = fn.replace(anchor, replacement, 1)
# EXP-F: leave both stock MVC canvas1 refresh branches untouched.  The proven
# synthetic NV21/MIF path reads VD2 from vd_if0_canvas0; test whether refreshing
# vd_if0_canvas1 for synthetic FP was historical baggage.  We still validate
# that the two stock MVC branches are present so the semantic anchor remains
# pinned to the expected source revision.
anchor = "\t\t\tif (is_mvc)\n\t\t\t\tcur_dev->rdma_func[vpp_index].rdma_wr\n\t\t\t\t\t(vd_mif_reg_mvc->vd_if0_canvas1,\n\t\t\t\t\tlayer->disp_canvas[cur_canvas_id][0]);\n"
canvas1_matches = fn.count(anchor)
if canvas1_matches != 2:
    raise SystemExit(
        f"ERROR: set_layer_display_canvas canvas1 anchors mismatch: "
        f"expected 2, found {canvas1_matches}"
    )
htxt = htxt[:start] + fn + htxt[end:]

# 8) Keep vd1_set_dcu() stock except for the MVC GEN2 reset below.
# Experiments F/G proved synthetic canvas1 refresh and synthetic vdx_path_select()
# are unnecessary: the progressive uncompressed path needs only VD2 canvas0 to
# follow VD1's current packed decode surface.
start, end, fn = function_slice(htxt, "static void vd1_set_dcu")
# Leave VD2 path selection stock/MVC-only.  EXP-G passed all tests, proving the
# explicit synthetic vdx_path_select(... MIF ...) extension is redundant.
anchor = "\tbool is_mvc = false;\n"
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: vd1_set_dcu local anchor mismatch: found {fn.count(anchor)}")
anchor = "\ttype = vf->type;\n"
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: vd1_set_dcu type anchor mismatch: found {fn.count(anchor)}")
anchor = "\t\tif (is_mvc)\n\t\t\tvdx_path_select(layer, false, false);\n"
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: vd1_set_dcu stock path-select anchor mismatch: found {fn.count(anchor)}")

# Keep the stock final VD2 GEN write MVC-only.  EXP-A proved synthetic GEN
# parity is unnecessary; the working synthetic steady state intentionally differs
# from MVC here.
anchor = "\tif (is_mvc)\n\t\tcur_dev->rdma_func[vpp_index].rdma_wr\n\t\t\t(vd2_mif_reg->vd_if0_gen_reg, r);\n"
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: vd1_set_dcu VD2 GEN stock anchor mismatch: found {fn.count(anchor)}")

# Synthetic packed playback uses NV21 and therefore leaves VD2 GEN_REG2[1:0]=1.
# Stock MVC reprograms most VD2 state but only writes the pixel-format bits to VD1,
# so the synthetic value can survive into later MVC playback and corrupt only the
# right eye.  Mirror the stock VD1 pixel-format programming onto VD2 for MVC.
anchor = "\tif (type & VIDTYPE_VIU_NV21)\n\t\tcur_dev->rdma_func[vpp_index].rdma_wr_bits\n\t\t\t(vd_mif_reg->vd_if0_gen_reg2, 1, 0, 2);\n\telse if (type & VIDTYPE_VIU_NV12)\n\t\tcur_dev->rdma_func[vpp_index].rdma_wr_bits\n\t\t\t(vd_mif_reg->vd_if0_gen_reg2, 2, 0, 2);\n\telse\n\t\tcur_dev->rdma_func[vpp_index].rdma_wr_bits\n\t\t\t(vd_mif_reg->vd_if0_gen_reg2, 0, 0, 2);\n"
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: vd1_set_dcu GEN2 pixel-format anchor mismatch: found {fn.count(anchor)}")
replacement = anchor + f"""\tif (is_mvc) {{
\t\t/* {MARK}: restore VD2 pixel-format bits after synthetic packed playback. */
\t\tif (type & VIDTYPE_VIU_NV21)
\t\t\tcur_dev->rdma_func[vpp_index].rdma_wr_bits
\t\t\t\t(vd2_mif_reg->vd_if0_gen_reg2, 1, 0, 2);
\t\telse if (type & VIDTYPE_VIU_NV12)
\t\t\tcur_dev->rdma_func[vpp_index].rdma_wr_bits
\t\t\t\t(vd2_mif_reg->vd_if0_gen_reg2, 2, 0, 2);
\t\telse
\t\t\tcur_dev->rdma_func[vpp_index].rdma_wr_bits
\t\t\t\t(vd2_mif_reg->vd_if0_gen_reg2, 0, 0, 2);
\t}}
"""
fn = fn.replace(anchor, replacement, 1)

htxt = htxt[:start] + fn + htxt[end:]

# 9) Keep VD2 in the same 3D compose state as real MVC.  Without this, the
# generic VPP blend updater sees VD2 with no independent dispbuf, repeatedly
# leaves it ON_PENDING / may disable it, which is exactly what v0.2.16 measured.
start, end, fn = function_slice(htxt, "void vpp_blend_update(")
anchor = "\tif (vd_layer[0].enable_3d_mode == mode_3d_mvc_enable)\n\t\tmode |= COMPOSE_MODE_3D;\n"
if fn.count(anchor) != 1:
    raise SystemExit(f"ERROR: vpp_blend_update 3D-mode anchor mismatch: found {fn.count(anchor)}")
replacement = f"""\tif (vd_layer[0].enable_3d_mode == mode_3d_mvc_enable ||
\t    ((process_3d_type & MODE_3D_FP) &&
\t     vd_layer[0].dispbuf &&
\t     !(vd_layer[0].dispbuf->type & VIDTYPE_MVC))) {{
\t\t/* {MARK}: only synthetic FP borrows MVC's companion-eye compose state. */
\t\tmode |= COMPOSE_MODE_3D;
\t}}
"""
fn = fn.replace(anchor, replacement, 1)
htxt = htxt[:start] + fn + htxt[end:]

# 10) Synthetic AFBC sharing/cropping is intentionally omitted.
# The proven FSBS/FTAB implementation uses the ordinary uncompressed MIF path.

# 11) Stock primary_render_frame() keys VD2 setup off last_mode_3d.  Synthetic
# MODE_3D_FP can reach this function before that legacy state reflects the new
# mode.  Gate the VD2 DCU/MIF/scaler/blend setup directly on synthetic_fp too.
ftxt = video_func.read_text()
if MARK in ftxt:
    print("FULL3D: video_func post-patch already present (v0.3.0-rc1)")
else:
    start, end, fn = function_slice(ftxt, "s32 primary_render_frame")
    anchor = "\tbool update_vd2 = false;\n\tstruct vframe_s *dispbuf = NULL;\n"
    if fn.count(anchor) != 1:
        raise SystemExit(f"ERROR: primary_render_frame local anchor mismatch: found {fn.count(anchor)}")
    replacement = "\tbool update_vd2 = false;\n\tbool synthetic_fp = false;\n\tstruct vframe_s *dispbuf = NULL;\n"
    fn = fn.replace(anchor, replacement, 1)


    anchor = "\telse\n\t\tdispbuf = layer->dispbuf;\n"
    if fn.count(anchor) != 1:
        raise SystemExit(f"ERROR: primary_render_frame dispbuf anchor mismatch: found {fn.count(anchor)}")
    replacement = f"""\telse
\t\tdispbuf = layer->dispbuf;
\tsynthetic_fp = dispbuf &&
\t\t(process_3d_type & MODE_3D_FP) &&
\t\t!(dispbuf->type & VIDTYPE_MVC);
"""
    fn = fn.replace(anchor, replacement, 1)

    anchor = "\t\tif (last_mode_3d &&\n\t\t    (layer->new_vpp_setting ||\n\t\t     afbc_need_reset))\n"
    if fn.count(anchor) != 1:
        raise SystemExit(f"ERROR: primary_render_frame VD2 DCU anchor mismatch: found {fn.count(anchor)}")
    replacement = "\t\tif ((last_mode_3d || synthetic_fp) &&\n\t\t    (layer->new_vpp_setting ||\n\t\t     afbc_need_reset))\n"
    fn = fn.replace(anchor, replacement, 1)

    anchor = "\t\tif ((dispbuf->type & VIDTYPE_MVC) ||\n\t\t    last_mode_3d) {\n"
    if fn.count(anchor) != 1:
        raise SystemExit(f"ERROR: primary_render_frame VD2 position anchor mismatch: found {fn.count(anchor)}")
    replacement = "\t\tif ((dispbuf->type & VIDTYPE_MVC) ||\n\t\t    last_mode_3d || synthetic_fp) {\n"
    fn = fn.replace(anchor, replacement, 1)

    anchor = "\tif ((dispbuf &&\n\t     (dispbuf->type & VIDTYPE_MVC)) ||\n\t    last_mode_3d) {\n"
    if fn.count(anchor) != 1:
        raise SystemExit(f"ERROR: primary_render_frame VD2 scaler/blend anchor mismatch: found {fn.count(anchor)}")
    replacement = "\tif ((dispbuf &&\n\t     (dispbuf->type & VIDTYPE_MVC)) ||\n\t    last_mode_3d || synthetic_fp) {\n"
    fn = fn.replace(anchor, replacement, 1)

    # A marker comment gives the semantic helper a reliable idempotence check.
    fn = fn.replace("s32 primary_render_frame(struct video_layer_s *layer,\n",
                    f"/* {MARK}: synthetic FP drives VD2 from the VD1 decode surface. */\n"
                    "s32 primary_render_frame(struct video_layer_s *layer,\n", 1)
    ftxt = ftxt[:start] + fn + ftxt[end:]

# Commit all files only after every semantic anchor validated successfully.
video_hw.write_text(htxt)
video_func.write_text(ftxt)
print("FULL3D: common_drivers post-patch completed (v0.3.0-rc1)")
