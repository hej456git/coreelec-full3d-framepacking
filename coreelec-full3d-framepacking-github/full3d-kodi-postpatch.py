#!/usr/bin/env python3
import re
import sys
from pathlib import Path

MARK = "FULL3D_FP_KODI_V030RC1"

if len(sys.argv) != 2:
    raise SystemExit("usage: full3d-kodi-postpatch.py <PKG_BUILD>")

root = Path(sys.argv[1])
aml = root / "xbmc/cores/VideoPlayer/DVDCodecs/Video/AMLCodec.cpp"
vpv = root / "xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp"
proc_h = root / "xbmc/cores/VideoPlayer/Process/ProcessInfo.h"
proc_cpp = root / "xbmc/cores/VideoPlayer/Process/ProcessInfo.cpp"
demux = root / "xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemuxFFmpeg.cpp"
settings_xml = root / "system/settings/settings.xml"
strings_en = root / "addons/resource.language.en_gb/resources/strings.po"
advanced = root / "xbmc/settings/AdvancedSettings.cpp"

for p in (aml, vpv, proc_h, proc_cpp, demux, settings_xml, strings_en, advanced):
    if not p.is_file():
        raise SystemExit(f"ERROR: expected Kodi source file not found: {p}")


def function_slice(text: str, start_token: str):
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
                state = "block_comment"; i += 2; continue
            if c == "/" and n == "/":
                state = "line_comment"; i += 2; continue
            if c == '"':
                state = "string"; i += 1; continue
            if c == "'":
                state = "char"; i += 1; continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    if end < len(text) and text[end] == "\n":
                        end += 1
                    return start, end, text[start:end]
            i += 1; continue
        if state == "block_comment":
            if c == "*" and n == "/":
                state = "code"; i += 2
            else:
                i += 1
            continue
        if state == "line_comment":
            if c == "\n": state = "code"
            i += 1; continue
        if state in ("string", "char"):
            quote = '"' if state == "string" else "'"
            if c == "\\": i += 2; continue
            if c == quote: state = "code"
            i += 1; continue
    raise SystemExit(f"ERROR: closing brace not found: {start_token}")


# --- ProcessInfo: private source-layout side channel ----------------------
# Keep Kodi's public stereo strings standard (left_right/top_bottom/block_lr),
# while carrying LR-vs-TB source packing separately to AMLCodec.
phtxt = proc_h.read_text()
if "SetFull3DSourceLayout" not in phtxt:
    old = "  void SetVideoStereoMode(const std::string &mode);\n  std::string GetVideoStereoMode();\n"
    if phtxt.count(old) != 1:
        raise SystemExit(f"ERROR: ProcessInfo.h stereo method anchor mismatch: found {phtxt.count(old)}")
    new = old + "  void SetFull3DSourceLayout(int layout);\n  int GetFull3DSourceLayout();\n"
    phtxt = phtxt.replace(old, new, 1)

    old_member = "  std::string m_videoStereoMode;\n"
    if phtxt.count(old_member) != 1:
        raise SystemExit(f"ERROR: ProcessInfo.h member anchor mismatch: found {phtxt.count(old_member)}")
    phtxt = phtxt.replace(old_member, old_member + "  int m_full3DSourceLayout = 0; // 0=none, 1=LR/SBS, 2=TB/TAB\n", 1)
    proc_h.write_text(phtxt)

pctxt = proc_cpp.read_text()
if "CProcessInfo::SetFull3DSourceLayout" not in pctxt:
    reset_anchor = "  m_videoStereoMode.clear();\n"
    if pctxt.count(reset_anchor) != 1:
        raise SystemExit(f"ERROR: ProcessInfo.cpp reset anchor mismatch: found {pctxt.count(reset_anchor)}")
    pctxt = pctxt.replace(reset_anchor, reset_anchor + "  m_full3DSourceLayout = 0;\n", 1)

    start, end, fn = function_slice(pctxt, "std::string CProcessInfo::GetVideoStereoMode")
    methods = '''\nvoid CProcessInfo::SetFull3DSourceLayout(int layout)\n{\n  std::unique_lock lock(m_videoCodecSection);\n  m_full3DSourceLayout = layout;\n}\n\nint CProcessInfo::GetFull3DSourceLayout()\n{\n  std::unique_lock lock(m_videoCodecSection);\n  return m_full3DSourceLayout;\n}\n'''
    pctxt = pctxt[:end] + methods + pctxt[end:]
    proc_cpp.write_text(pctxt)


# --- DVDDemuxFFmpeg.cpp --------------------------------------------------
# Preserve an explicit FSBS/FTAB filename declaration as a private stream hint.
# VideoThumbLoader still exposes the standard left_right/top_bottom mode to UI.
dtxt = demux.read_text()
if "FULL3D_EXPLICIT_FILENAME_V027" not in dtxt:
    start, end, fn = function_slice(dtxt, "CDemuxStream* CDVDDemuxFFmpeg::AddStream")
    pattern = re.compile(r"(?P<indent>^[ \t]*)st->stereo_mode\s*=\s*stereoMode;[ \t]*$", re.MULTILINE)
    matches = list(pattern.finditer(fn))
    if len(matches) != 1:
        raise SystemExit(f"ERROR: DVDDemuxFFmpeg stereo_mode anchor mismatch: found {len(matches)}")
    m = matches[0]
    indent = m.group("indent")
    insert = f'''\n\n{indent}// FULL3D_EXPLICIT_FILENAME_V027: FSBS/FTAB is an explicit declaration.\n{indent}// Keep this as a private stream hint so normal Kodi SBS/TAB behaviour is unchanged.\n{indent}if (m_pInput)\n{indent}{{\n{indent}  std::string full3dName = m_pInput->GetFileName();\n{indent}  StringUtils::ToLower(full3dName);\n{indent}  const auto hasTag = [&full3dName](const std::string& tag)\n{indent}  {{\n{indent}    auto boundary = [](char c) {{ return c == '.' || c == '_' || c == '-' || c == ' '; }};\n{indent}    size_t pos = 0;\n{indent}    while ((pos = full3dName.find(tag, pos)) != std::string::npos)\n{indent}    {{\n{indent}      const size_t after = pos + tag.size();\n{indent}      const bool leftOk = pos == 0 || boundary(full3dName[pos - 1]);\n{indent}      const bool rightOk = after == full3dName.size() || boundary(full3dName[after]);\n{indent}      if (leftOk && rightOk)\n{indent}        return true;\n{indent}      pos = after;\n{indent}    }}\n{indent}    return false;\n{indent}  }};\n\n{indent}  if (hasTag("fsbs"))\n{indent}    st->stereo_mode = "full_left_right";\n{indent}  else if (hasTag("ftab"))\n{indent}    st->stereo_mode = "full_top_bottom";\n{indent}}}\n'''
    insert_pos = m.end()
    fn = fn[:insert_pos] + insert + fn[insert_pos:]
    dtxt = dtxt[:start] + fn + dtxt[end:]
    demux.write_text(dtxt)


# --- AMLCodec.cpp ---------------------------------------------------------
atxt = aml.read_text()
if MARK not in atxt:
    anchor = "#define MODE_3D_OUT_LR          0x00020000\n"
    if atxt.count(anchor) != 1:
        raise SystemExit(f"ERROR: AMLCodec mode-define anchor mismatch: found {atxt.count(anchor)}")
    atxt = atxt.replace(
        anchor,
        anchor
        + "#define MODE_FORCE_3D_LR        0x01000000\n"
        + "#define MODE_FORCE_3D_TB        0x02000000\n"
        + "#define MODE_3D_FP              0x04000000  // " + MARK + "\n",
        1,
    )

    start, end, fn = function_slice(atxt, "void CAMLCodec::SetVideoRect")
    old = """      default:\n        aml_set_3d_video_mode(MODE_3D_DISABLE, false, mvc_view_mode);\n        break;\n"""
    if fn.count(old) != 1:
        raise SystemExit(f"ERROR: CAMLCodec::SetVideoRect default anchor mismatch: found {fn.count(old)}")
    new = f"""      default:\n        {{\n          unsigned int packed3d_mode = MODE_3D_DISABLE;\n          const std::string videoStereoMode = m_processInfo.GetVideoStereoMode();\n          const int full3dSourceLayout = m_processInfo.GetFull3DSourceLayout();\n\n          if (m_guiStereoMode == RenderStereoMode::HARDWAREBASED &&\n              (videoStereoMode == \"block_lr\" || videoStereoMode == \"block_rl\"))\n          {{\n            if (full3dSourceLayout == 1)\n              packed3d_mode = MODE_3D_ENABLE | MODE_FORCE_3D_LR | MODE_3D_FP;\n            else if (full3dSourceLayout == 2)\n              packed3d_mode = MODE_3D_ENABLE | MODE_FORCE_3D_TB | MODE_3D_FP;\n\n            if (packed3d_mode != MODE_3D_DISABLE && videoStereoMode == \"block_rl\")\n              packed3d_mode |= MODE_3D_LR_SWITCH;\n          }}\n\n          if (packed3d_mode != MODE_3D_DISABLE)\n            CLog::Log(LOGINFO,\n                      \"CAMLCodec: full-resolution packed 3D -> HDMI frame packing, layout={{}}, mode=0x{{:x}}\",\n                      full3dSourceLayout, packed3d_mode);\n\n          // {MARK}: false is intentional. The decoded source has no HDMI\n          // frame-packing blank lines; common_drivers creates that geometry.\n          aml_set_3d_video_mode(packed3d_mode, false, mvc_view_mode);\n          break;\n        }}\n"""
    fn = fn.replace(old, new, 1)

    # Full-resolution SBS/TAB has a packed-frame aspect ratio (32:9 or 8:9),
    # but HARDWAREBASED frame packing must size the destination from one 16:9 eye.
    # Stock Kodi computes DestRect from the packed aspect first, then only extends y2
    # for FP.  That leaves FSBS letterboxed at y=270 and FTAB pillarboxed/narrow.
    axis_old = """  else if (m_guiStereoMode == RenderStereoMode::HARDWAREBASED)
  {
    // 3D frame packed output: get the screen height from the graphic context
    // (will work in fullscreen mode only)
    RESOLUTION_INFO info = CServiceBroker::GetWinSystem()->GetGfxContext().GetResInfo();
    dst_rect.y2 = info.iHeight * 2 + info.iBlanking;
  }
"""
    if fn.count(axis_old) != 1:
        raise SystemExit(f"ERROR: CAMLCodec HARDWAREBASED axis anchor mismatch: found {fn.count(axis_old)}")
    axis_new = f"""  else if (m_guiStereoMode == RenderStereoMode::HARDWAREBASED)
  {{
    // 3D frame packed output: get the screen height from the graphic context
    // (will work in fullscreen mode only)
    RESOLUTION_INFO info = CServiceBroker::GetWinSystem()->GetGfxContext().GetResInfo();
    const int full3dSourceLayout = m_processInfo.GetFull3DSourceLayout();
    if (full3dSourceLayout != 0)
    {{
      // {MARK}: packed FSBS/FTAB aspect belongs to the transport, not one eye.
      // Use the full 16:9 display width/height as the per-eye destination before
      // extending the canvas to 1080 + blank + 1080 frame-packed timing.
      dst_rect.x1 = display.x1;
      dst_rect.x2 = display.x2;
      dst_rect.y1 = display.y1;
      CLog::Log(LOGINFO,
                "Full3D: correcting packed destination rectangle to full-eye frame before FP (layout={{}})",
                full3dSourceLayout);
    }}
    dst_rect.y2 = info.iHeight * 2 + info.iBlanking;
  }}
"""
    fn = fn.replace(axis_old, axis_new, 1)

    atxt = atxt[:start] + fn + atxt[end:]

    # v0.2.23: SetVideoRect runs on the renderer thread and can race with
    # CloseDecoder(). Once codec_close has set m_opened=false, a late renderer
    # callback must not re-enable the video plane or write the old 2205-line
    # frame-packed axis back after the GUI/display has returned to 2D.
    start, end, fn = function_slice(atxt, "void CAMLCodec::SetVideoRect")
    teardown_anchor = "  // this routine gets called every video frame\n"
    if fn.count(teardown_anchor) != 1:
        raise SystemExit(f"ERROR: CAMLCodec::SetVideoRect teardown anchor mismatch: found {fn.count(teardown_anchor)}")
    teardown_guard = (
        "  // FULL3D_FP_KODI_TEARDOWN_V023: renderer teardown can race decoder close.\n"
        "  // Never re-show the video plane or re-apply a stale frame-packed axis after\n"
        "  // CloseDecoder() has marked the codec closed.\n"
        "  if (!m_opened)\n"
        "  {\n"
        "    ShowMainVideo(false);\n"
        "    return;\n"
        "  }\n\n"
    )
    fn = fn.replace(teardown_anchor, teardown_guard + teardown_anchor, 1)
    atxt = atxt[:start] + fn + atxt[end:]

    # Normalize the stored video axis when closing. /sys/class/video/axis is a
    # software window (glayer_info), and can otherwise remain 0..2204 after FP
    # even though HDMI/vout has already returned to a normal 1080-line mode.
    start, end, fn = function_slice(atxt, "void CAMLCodec::CloseDecoder")
    close_anchor = "  ShowMainVideo(false);\n\n  CloseAmlVideo();\n"
    if fn.count(close_anchor) != 1:
        raise SystemExit(f"ERROR: CAMLCodec::CloseDecoder teardown anchor mismatch: found {fn.count(close_anchor)}")
    close_reset = (
        "  ShowMainVideo(false);\n\n"
        "  // FULL3D_FP_KODI_TEARDOWN_V023: leave the hidden video plane with sane\n"
        "  // 2D geometry. This also makes the next decoder session independent of the\n"
        "  // preceding 2205-line frame-packed window.\n"
        "  m_processInfo.SetFull3DSourceLayout(0);\n"
        "  const RESOLUTION closeVideoRes =\n"
        "      CServiceBroker::GetWinSystem()->GetGfxContext().GetVideoResolution();\n"
        "  const RESOLUTION_INFO& closeInfo =\n"
        "      CDisplaySettings::GetInstance().GetResolutionInfo(closeVideoRes);\n"
        "  if (closeInfo.iScreenWidth > 0 && closeInfo.iScreenHeight > 0)\n"
        "  {\n"
        "    char closeVideoAxis[64] = {};\n"
        "    snprintf(closeVideoAxis, sizeof(closeVideoAxis), \"0 0 %d %d\",\n"
        "             closeInfo.iScreenWidth - 1, closeInfo.iScreenHeight - 1);\n"
        "    CSysfsPath(\"/sys/class/video/axis\", closeVideoAxis);\n"
        "  }\n\n"
        "  CloseAmlVideo();\n"
    )
    fn = fn.replace(close_anchor, close_reset, 1)
    atxt = atxt[:start] + fn + atxt[end:]

    aml.write_text(atxt)


# --- VideoPlayerVideo.cpp -------------------------------------------------
vtxt = vpv.read_text()
if MARK not in vtxt:
    include_anchor = '#include "settings/SettingsComponent.h"\n'
    render_include = '#include "rendering/RenderSystem.h"\n'
    if render_include not in vtxt:
        if vtxt.count(include_anchor) != 1:
            raise SystemExit(f"ERROR: VideoPlayerVideo include anchor mismatch: found {vtxt.count(include_anchor)}")
        vtxt = vtxt.replace(include_anchor, include_anchor + render_include, 1)

    start, end, fn = function_slice(vtxt, "bool CVideoPlayerVideo::ProcessDecoderOutput")
    anchor = "    // if frame has a pts (usually originating from demux packet), use that\n"
    if fn.count(anchor) != 1:
        raise SystemExit(f"ERROR: ProcessDecoderOutput PTS anchor mismatch: found {fn.count(anchor)}")
    block = f'''    // {MARK}: selectable conversion of full-resolution packed stereo to\n    // the existing hardware/frame-packed mode. Explicit FSBS/FTAB filename\n    // hints are authoritative; ordinary SBS/TAB still requires canonical\n    // full-resolution geometry. Policy: 0=Auto, 1=Keep SBS/TAB, 2=Frame packed.\n    const int full3dOutput = CServiceBroker::GetSettingsComponent()->GetSettings()->GetInt(\n        "videoscreen.full3doutput");\n    const bool full3dHardwareSupported = CServiceBroker::GetRenderSystem() &&\n        CServiceBroker::GetRenderSystem()->SupportsStereo(RenderStereoMode::HARDWAREBASED);\n    const bool full3dUseFramePacking =\n        full3dOutput == 2 || (full3dOutput == 0 && full3dHardwareSupported);\n\n    int full3dSourceLayout = 0; // 0=none, 1=LR/SBS, 2=TB/TAB
    bool full3dExplicit = false;

    // Kodi can already have mapped the public stereo string to block_lr/block_rl
    // for HARDWAREBASED output before this hook runs. Use demux intent plus
    // canonical full-resolution geometry so source layout is not lost.
    const auto configuredStereoMode =
        static_cast<RenderStereoMode>(m_processInfo.GetVideoSettings().m_StereoMode);
    const bool full3dHardwareIntent =
        configuredStereoMode == RenderStereoMode::HARDWAREBASED ||
        m_picture.stereoMode == "block_lr" || m_picture.stereoMode == "block_rl";
    const bool full3dSbsIntent =
        m_hints.stereo_mode == "left_right" || m_hints.stereo_mode == "right_left" ||
        m_hints.stereo_mode == "full_left_right" ||
        m_picture.stereoMode == "left_right" || m_picture.stereoMode == "right_left" ||
        (full3dHardwareIntent && m_picture.iWidth == 3840 && m_picture.iHeight == 1080);
    const bool full3dTabIntent =
        m_hints.stereo_mode == "top_bottom" || m_hints.stereo_mode == "bottom_top" ||
        m_hints.stereo_mode == "full_top_bottom" ||
        m_picture.stereoMode == "top_bottom" || m_picture.stereoMode == "bottom_top" ||
        (full3dHardwareIntent && m_picture.iWidth == 1920 && m_picture.iHeight == 2160);

    if (m_hints.stereo_mode == "full_left_right")
    {{
      full3dSourceLayout = 1;
      full3dExplicit = true;
      m_picture.stereoMode = "left_right";
    }}
    else if (m_hints.stereo_mode == "full_top_bottom")
    {{
      full3dSourceLayout = 2;
      full3dExplicit = true;
      m_picture.stereoMode = "top_bottom";
    }}
    else if (m_picture.iWidth == 3840 && m_picture.iHeight == 1080 && full3dSbsIntent)
    {{
      full3dSourceLayout = 1;
    }}
    else if (m_picture.iWidth == 1920 && m_picture.iHeight == 2160 && full3dTabIntent)
    {{
      full3dSourceLayout = 2;
    }}

    bool full3dGeometrySane = full3dSourceLayout != 0;\n    if (full3dExplicit && full3dSourceLayout == 1)\n    {{\n      full3dGeometrySane = m_picture.iWidth > 0 && m_picture.iHeight > 0 &&\n                           (m_picture.iWidth % 2) == 0 &&\n                           (m_picture.iWidth / 2) <= 1920 && m_picture.iHeight <= 1080;\n    }}\n    else if (full3dExplicit && full3dSourceLayout == 2)\n    {{\n      full3dGeometrySane = m_picture.iWidth > 0 && m_picture.iHeight > 0 &&\n                           (m_picture.iHeight % 2) == 0 &&\n                           m_picture.iWidth <= 1920 && (m_picture.iHeight / 2) <= 1080;\n    }}\n\n    if (full3dExplicit && !full3dGeometrySane)\n    {{\n      CLog::Log(LOGWARNING,\n                "Full3D: explicit FSBS/FTAB marker has unsupported geometry {{}}x{{}}; keeping normal SBS/TAB output",\n                m_picture.iWidth, m_picture.iHeight);\n    }}\n\n    if (full3dUseFramePacking && full3dGeometrySane)\n    {{\n      if (m_processInfo.GetFull3DSourceLayout() != full3dSourceLayout)
      {{
        CLog::Log(LOGINFO,
                  "Full3D: selected layout={{}} for {{}}x{{}} source (hint='{{}}', picture='{{}}', configured={{}})",
                  full3dSourceLayout, m_picture.iWidth, m_picture.iHeight,
                  m_hints.stereo_mode, m_picture.stereoMode,
                  static_cast<int>(configuredStereoMode));
      }}
      m_processInfo.SetFull3DSourceLayout(full3dSourceLayout);\n      if (full3dSourceLayout == 1)\n      {{\n        if (m_picture.stereoMode == "left_right")\n          m_picture.stereoMode = "block_lr";\n        else if (m_picture.stereoMode == "right_left")\n          m_picture.stereoMode = "block_rl";\n      }}\n      else if (full3dSourceLayout == 2)\n      {{\n        if (m_picture.stereoMode == "top_bottom")\n          m_picture.stereoMode = "block_lr";\n        else if (m_picture.stereoMode == "bottom_top")\n          m_picture.stereoMode = "block_rl";\n      }}\n\n      if (full3dExplicit)\n        CLog::Log(LOGINFO, "Full3D: explicit filename marker selected layout={{}} for {{}}x{{}} source",\n                  full3dSourceLayout, m_picture.iWidth, m_picture.iHeight);\n    }}\n    else\n    {{\n      m_processInfo.SetFull3DSourceLayout(0);\n    }}\n\n'''
    fn = fn.replace(anchor, block + anchor, 1)
    vtxt = vtxt[:start] + fn + vtxt[end:]
    vpv.write_text(vtxt)


# --- settings.xml ---------------------------------------------------------
stxt = settings_xml.read_text()
setting_id = 'videoscreen.full3doutput'
if setting_id not in stxt:
    anchor = '''        <setting id="videoscreen.preferedstereoscopicmode" parent="videoscreen.stereoscopicmode" type="integer" label="36524" help="36540">\n          <level>2</level>\n          <default>100</default> <!-- ENUM RENDER_STEREO_MODE_AUTO -->\n          <constraints>\n            <options>preferedstereoscopicviewmodes</options>\n          </constraints>\n          <updates>\n            <update type="change" />\n          </updates>\n          <control type="list" format="integer"/>\n        </setting>\n'''
    if stxt.count(anchor) != 1:
        raise SystemExit(f"ERROR: settings.xml stereo anchor mismatch: found {stxt.count(anchor)}")
    addition = anchor + '''        <setting id="videoscreen.full3doutput" parent="videoscreen.stereoscopicmode" type="integer" label="39050" help="39051">\n          <level>3</level>\n          <default>0</default> <!-- Auto -->\n          <constraints>\n            <options>\n              <option label="13416">0</option> <!-- Auto -->\n              <option label="39052">1</option> <!-- Keep SBS/TAB -->\n              <option label="39053">2</option> <!-- Frame packed -->\n            </options>\n          </constraints>\n          <control type="list" format="string"/>\n        </setting>\n'''
    stxt = stxt.replace(anchor, addition, 1)
    settings_xml.write_text(stxt)


# --- English strings ------------------------------------------------------
ltext = strings_en.read_text()
if 'msgctxt "#39050"' not in ltext:
    ltext += '''\n\n#. Full-resolution stereoscopic output policy\n#: system/settings/settings.xml\nmsgctxt "#39050"\nmsgid "Full-resolution SBS/TAB output"\nmsgstr ""\n\n#. Help for full-resolution stereoscopic output policy\n#: system/settings/settings.xml\nmsgctxt "#39051"\nmsgid "Choose whether full-resolution side-by-side and top-and-bottom video is kept in its packed format or converted to HDMI frame-packed 3D. Auto uses frame packing when the render system reports hardware-based stereo support. Explicit FSBS/FTAB filename markers declare a full-resolution source; ordinary SBS/TAB is only auto-promoted at canonical full-resolution geometry."\nmsgstr ""\n\n#: system/settings/settings.xml\nmsgctxt "#39052"\nmsgid "Keep SBS/TAB"\nmsgstr ""\n\n#: system/settings/settings.xml\nmsgctxt "#39053"\nmsgid "Frame packed"\nmsgstr ""\n'''
    strings_en.write_text(ltext)


# --- AdvancedSettings.cpp filename stereo detection -----------------------
# Extend stock SBS/HSBS and TAB/HTAB detection to FSBS/FTAB. The demuxer
# separately preserves explicit F-tags as a private playback hint.
adtxt = advanced.read_text()
old_sbs = 'm_stereoscopicregex_sbs = "[-. _]h?sbs[-. _]";'
new_sbs = 'm_stereoscopicregex_sbs = "[-. _][fh]?sbs[-. _]";'
old_tab = 'm_stereoscopicregex_tab = "[-. _]h?tab[-. _]";'
new_tab = 'm_stereoscopicregex_tab = "[-. _][fh]?tab[-. _]";'

if old_sbs in adtxt:
    adtxt = adtxt.replace(old_sbs, new_sbs, 1)
elif new_sbs not in adtxt:
    raise SystemExit("ERROR: AdvancedSettings.cpp SBS regex anchor not found")

if old_tab in adtxt:
    adtxt = adtxt.replace(old_tab, new_tab, 1)
elif new_tab not in adtxt:
    raise SystemExit("ERROR: AdvancedSettings.cpp TAB regex anchor not found")

advanced.write_text(adtxt)

print("FULL3D: Kodi post-patch completed (v0.3.0-rc1)")
