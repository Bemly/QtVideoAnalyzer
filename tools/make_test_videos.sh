#!/bin/bash
# 一键生成编码器测试视频 (~5s, 640x360, 30fps, 运动 + 场景闪切)。
# 用法: bash tools/make_test_videos.sh   (在仓库根目录执行)
# 依赖: ffmpeg / ffprobe (本机实测 /opt/homebrew/bin/ffmpeg 9.0.2)
set -u

FFMPEG="${FFMPEG:-ffmpeg}"
OUTDIR="${OUTDIR:-tools/samples}"
DUR=5; W=640; H=360; FPS=30

# 运动(testsrc2) + 每 2.5s 一次整帧红闪(≈1 帧, 充当场景切换, 便于观察 I/P/B)
VF="testsrc2=size=${W}x${H}:rate=${FPS}:duration=${DUR},drawbox=c=red:t=fill:enable='lt(mod(t+1.25,2.5),0.034)':x=0:y=0:w=iw:h=ih,format=yuv420p"
AF="sine=frequency=440:duration=${DUR}:sample_rate=44100"

mkdir -p "$OUTDIR"

OK=0; SKIP=0; FAIL=0

have_encoder() {  # $1: encoder 名
  "$FFMPEG" -hide_banner -encoders 2>/dev/null | grep -qw "$1"
}

gen() {  # $1: 描述  $2: 输出文件名  $@(3+): 编解码参数
  local desc="$1" out="$2"; shift 2
  if [ -e "$OUTDIR/$out" ] && [ "${FORCE:-0}" != "1" ]; then
    echo "[exists] $desc -> $OUTDIR/$out (FORCE=1 可重建)"
    OK=$((OK+1)); return 0
  fi
  echo "==> $desc -> $OUTDIR/$out"
  if "$FFMPEG" -hide_banner -y -v warning -stats \
      -f lavfi -i "$VF" -f lavfi -i "$AF" \
      -t "$DUR" -r "$FPS" "$@" "$OUTDIR/$out"; then
    OK=$((OK+1))
  else
    echo "[FAIL] $desc"
    rm -f "$OUTDIR/$out"
    FAIL=$((FAIL+1))
  fi
}

need() {  # $1: encoder  $2: 描述
  if ! have_encoder "$1"; then
    echo "[SKIP] $2: 本机 ffmpeg 无编码器 '$1'"
    SKIP=$((SKIP+1)); return 1
  fi
  return 0
}

# 1. AVC / H.264
need libx264 "avc" && \
gen "avc (libx264)" test_avc.mp4 \
  -c:v libx264 -pix_fmt yuv420p -preset veryfast -g 30 -bf 2 -c:a aac -b:a 128k

# 2. HEVC / H.265
need libx265 "hevc" && \
gen "hevc (libx265)" test_hevc.mp4 \
  -c:v libx265 -pix_fmt yuv420p -preset veryfast -g 30 -bf 2 -c:a aac -b:a 128k

# 3. MPEG-2 (mpg 容器音频需 mp2)
need mpeg2video "mpeg2" && \
gen "mpeg2 (mpeg2video)" test_mpeg2.mpg \
  -c:v mpeg2video -pix_fmt yuv420p -g 12 -bf 2 -b:v 2M -c:a mp2 -b:a 128k

# 4. Theora
need libtheora "theora" && \
gen "theora (libtheora)" test_theora.ogv \
  -c:v libtheora -pix_fmt yuv420p -b:v 1M -c:a libvorbis -b:a 128k

# 5. AV1: 本机优先 libaom-av1, 否则 libsvtav1
if have_encoder libaom-av1; then
  gen "av1 (libaom-av1)" test_av1.mp4 \
    -c:v libaom-av1 -pix_fmt yuv420p -cpu-used 8 -crf 30 -b:v 0 -g 30 -c:a aac -b:a 128k
elif have_encoder libsvtav1; then
  gen "av1 (libsvtav1)" test_av1.mp4 \
    -c:v libsvtav1 -pix_fmt yuv420p -preset 8 -crf 32 -g 30 -c:a aac -b:a 128k
else
  echo "[SKIP] av1: 无 libaom-av1 / libsvtav1"
  SKIP=$((SKIP+1))
fi

# 6. H.263 (baseline 仅支持固定尺寸, 故用 H.263+ / h263p 编码器;
#    标准 H.263 无 B 帧, 此处同样无 B 帧预期)
{ need h263p "h263" || need h263 "h263(h263)"; } && \
gen "h263 (h263p/H.263+ baseline 兼容)" test_h263.mov \
  -c:v h263p -pix_fmt yuv420p -b:v 1M -c:a aac -b:a 128k

# 7. VP6 (flash): 上游 ffmpeg 已无 vp6 编码器, 预期跳过
need vp6f "vp6" && \
gen "vp6 (vp6f)" test_vp6.flv \
  -c:v vp6f -pix_fmt yuv420p -b:v 1M -c:a mp3 -b:a 128k

# 8. VP8
need libvpx "vp8" && \
gen "vp8 (libvpx)" test_vp8.webm \
  -c:v libvpx -pix_fmt yuv420p -b:v 1M -g 30 -auto-alt-ref 1 -lag-in-frames 25 -c:a libopus -b:a 96k

# 9. VP9
need libvpx-vp9 "vp9" && \
gen "vp9 (libvpx-vp9)" test_vp9.webm \
  -c:v libvpx-vp9 -pix_fmt yuv420p -b:v 1M -g 30 -bf 3 -auto-alt-ref 1 -lag-in-frames 25 -c:a libopus -b:a 96k

echo
echo "===== done: ok=$OK skip=$SKIP fail=$FAIL ====="
ls -la "$OUTDIR"
[ "$FAIL" -eq 0 ]
