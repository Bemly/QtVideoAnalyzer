#!/usr/bin/env bash
# Retranscode all testsrc2-based local variants from a real 3D clip
# (Sintel trailer, camera pans + stops) keeping profile/chroma/RC settings.
# Usage: ./tools/retranscode_from_sintel.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
SRC="$ROOT/tools/samples/test_avc_sintel_trailer.mp4"
SEG="-ss 5 -t 5"
S360="scale=640:360:flags=lanczos"
cd "$ROOT"
[ -f "$SRC" ] || { echo "missing $SRC"; exit 1; }

echo "== AVC =="
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libx264 -profile:v baseline -pix_fmt yuv420p -b:v 1M -maxrate 1M -bufsize 2M tools/samples/test_avc_baseline_420.mp4
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libx264 -profile:v main -pix_fmt yuv420p -crf 23 tools/samples/test_avc_main_420_crf.mp4
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libx264 -profile:v high422 -pix_fmt yuv422p -crf 20 tools/samples/test_avc_high_422.mp4

echo "== HEVC =="
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libx265 -pix_fmt yuv420p -crf 28 tools/samples/test_hevc_main_420.mp4
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libx265 -pix_fmt yuv420p10le -crf 28 tools/samples/test_hevc_main10_420.mp4
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libx265 -pix_fmt yuv422p10le -crf 28 tools/samples/test_hevc_main422_10.mp4
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libx265 -pix_fmt yuv420p -b:v 3M -maxrate 3M -bufsize 6M tools/samples/test_hevc_main_cbr.mp4

echo "== MPEG-2 =="
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "scale=720:576" -an -c:v mpeg2video -pix_fmt yuv420p -b:v 6M -minrate 6M -maxrate 6M -bufsize 12M -g 12 -bf 2 tools/samples/test_mpeg2_main_420_cbr.mpg
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "scale=720:576" -an -c:v mpeg2video -pix_fmt yuv422p -b:v 8M -maxrate 12M -bufsize 16M -g 12 -bf 2 tools/samples/test_mpeg2_422_vbr.mpg
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "scale=720:576,setfield=tff" -an -c:v mpeg2video -pix_fmt yuv420p -flags +ildct+ilme -b:v 6M -maxrate 9M -bufsize 12M -g 12 -bf 2 tools/samples/test_mpeg2_main_interlaced.mpg

echo "== AV1 =="
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libsvtav1 -preset 8 -pix_fmt yuv420p -crf 32 -g 30 tools/samples/test_av1_main8_crf.mp4
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libsvtav1 -preset 8 -pix_fmt yuv420p10le -b:v 800k tools/samples/test_av1_main10_vbr.mp4
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libsvtav1 -preset 8 -pix_fmt yuv420p -b:v 800k -maxrate 800k -bufsize 800k -svtav1-params pred-struct=1:rc=2 tools/samples/test_av1_cbr_ld.mp4

echo "== H.263 =="
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "scale=176:144" -an -c:v h263 -pix_fmt yuv420p -b:v 128k -maxrate 128k -bufsize 256k -g 30 tools/samples/test_h263_qcif_cbr.mov
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "scale=352:288" -an -c:v h263 -pix_fmt yuv420p -q:v 3 -g 30 tools/samples/test_h263_cif_vbr.mov
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "scale=352:288" -an -c:v h263p -pix_fmt yuv420p -umv 1 -aiv 1 -b:v 1M -g 30 tools/samples/test_h263plus_annex.mov

echo "== VP8 =="
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libvpx -pix_fmt yuv420p -b:v 1500k -minrate 1500k -maxrate 1500k -bufsize 1500k -deadline realtime -cpu-used 5 -lag-in-frames 0 -auto-alt-ref 0 tools/samples/test_vp8_cbr_realtime.webm
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libvpx -pix_fmt yuv420p -b:v 2M -maxrate 3M -bufsize 4M -deadline good -cpu-used 2 -auto-alt-ref 1 -lag-in-frames 25 -pass 1 -passlogfile /tmp/vp8_vbr -f null /dev/null
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libvpx -pix_fmt yuv420p -b:v 2M -maxrate 3M -bufsize 4M -deadline good -cpu-used 2 -auto-alt-ref 1 -lag-in-frames 25 -pass 2 -passlogfile /tmp/vp8_vbr tools/samples/test_vp8_vbr_2pass.webm
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libvpx -pix_fmt yuv420p -b:v 0 -crf 10 -deadline good -cpu-used 2 tools/samples/test_vp8_cq.webm

echo "== VP9 =="
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libvpx-vp9 -profile:v 0 -pix_fmt yuv420p -b:v 2M -minrate 2M -maxrate 2M -bufsize 2M -deadline realtime -cpu-used 5 -auto-alt-ref 0 -lag-in-frames 0 -tile-columns 1 -row-mt 1 tools/samples/test_vp9_p0_cbr.webm
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libvpx-vp9 -profile:v 2 -pix_fmt yuv420p10le -b:v 1500k -maxrate 2250k -bufsize 3000k -deadline good -cpu-used 2 -auto-alt-ref 1 tools/samples/test_vp9_p2_10bit.webm
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v libvpx-vp9 -profile:v 1 -pix_fmt yuv444p -b:v 0 -crf 30 -deadline good -cpu-used 2 tools/samples/test_vp9_p1_444.webm

echo "== ProRes =="
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v prores_ks -profile:v 0 -pix_fmt yuv422p10le tools/samples/test_prores_proxy.mov
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v prores_ks -profile:v 1 -pix_fmt yuv422p10le tools/samples/test_prores_lt.mov
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v prores_ks -profile:v 3 -pix_fmt yuv422p10le tools/samples/test_prores_hq.mov
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v prores_ks -profile:v 4 -pix_fmt yuv444p10le tools/samples/test_prores_4444.mov
ffmpeg -hide_banner -loglevel error -y $SEG -i "$SRC" -vf "$S360" -an -c:v prores_ks -profile:v 5 -pix_fmt yuv444p10le tools/samples/test_prores_4444xq.mov

echo ALL DONE
