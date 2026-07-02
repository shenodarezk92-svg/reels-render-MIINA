from flask import Flask, request, jsonify, send_file
import subprocess, os, requests, tempfile, uuid, traceback
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont
import textwrap

app = Flask(__name__)
@app.route('/health', methods=['GET'])
def health():
    return {'status': 'alive'}, 200
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# خط افتراضي متوفر على أغلب أنظمة لينكس (Render يستخدم Debian)
# لو عايزين خط عربي أو خط مخصص، حطوه في الريبو وحدّثوا المسار هنا
DEFAULT_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def get_font(size):
    for path in DEFAULT_FONT_PATHS:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    # fallback لو مفيش أي خط متاح (شكل الخط هيبقى بسيط جداً)
    return ImageFont.load_default()


def download_file(url, suffix):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(r.content)
    tmp.close()
    return tmp.name


def draw_text_on_image(img_path, main_text, channel_name, out_path):
    """
    بيفتح الصورة، يعمل لها resize/crop لـ 1080x1920 (نفس اللي كان بيعمله scale+crop في ffmpeg)،
    وبعدين يرسم النص الرئيسي في النص، واسم القناة تحت.
    """
    img = Image.open(img_path).convert("RGB")

    target_w, target_h = 1080, 1920
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = int(src_w * scale), int(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))

    draw = ImageDraw.Draw(img)

    # --- النص الرئيسي في النص، مع لف تلقائي ---
    main_font = get_font(55)
    wrapped = textwrap.fill(main_text, width=22)  # عدّلوا width حسب طول النص المتوقع
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=main_font, align="center")
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (target_w - text_w) / 2
    y = (target_h - text_h) / 2

    # ظل خفيف عشان الوضوح فوق أي خلفية
    shadow_offset = 3
    draw.multiline_text((x + shadow_offset, y + shadow_offset), wrapped,
                         font=main_font, fill="black", align="center")
    draw.multiline_text((x, y), wrapped, font=main_font, fill="white", align="center")

    # --- اسم القناة تحت ---
    small_font = get_font(34)
    bbox2 = draw.textbbox((0, 0), channel_name, font=small_font)
    cw = bbox2[2] - bbox2[0]
    cx = (target_w - cw) / 2
    cy = target_h - 90
    draw.text((cx + 2, cy + 2), channel_name, font=small_font, fill="black")
    draw.text((cx, cy), channel_name, font=small_font, fill="white")

    img.save(out_path, quality=95)


@app.route('/render', methods=['POST'])
def render():
    try:
        data = request.json
        scenes = data['scenes']
        music_url = data['music_url']
        channel_name = data.get('channel_name', 'MIINA')

        music_path = download_file(music_url, '.mp3')
        scene_videos = []

        for i, scene in enumerate(scenes):
            img_path = download_file(scene['image_url'], '.jpg')
            audio_path = download_file(scene['audio_url'], '.mp3')
            text = scene['text']

            processed_img = f'/tmp/frame_{i}.jpg'
            draw_text_on_image(img_path, text, channel_name, processed_img)

            out = f'/tmp/scene_{i}.mp4'
            cmd = [
                FFMPEG, '-y',
                '-loop', '1', '-i', processed_img,
                '-i', audio_path,
                '-vf', 'scale=1080:1920',
                '-shortest', '-c:v', 'libx264', '-c:a', 'aac', '-pix_fmt', 'yuv420p',
                out
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return jsonify({'error': result.stderr}), 500

            scene_videos.append(out)
            os.unlink(img_path)
            os.unlink(audio_path)
            os.unlink(processed_img)

        list_file = '/tmp/list.txt'
        with open(list_file, 'w') as f:
            for v in scene_videos:
                f.write(f"file '{v}'\n")

        concat_out = '/tmp/concat.mp4'
        subprocess.run([FFMPEG, '-y', '-f', 'concat', '-safe', '0',
                       '-i', list_file, '-c', 'copy', concat_out], check=True)

        final_out = f'/tmp/final_{uuid.uuid4().hex}.mp4'
        subprocess.run([
            FFMPEG, '-y', '-i', concat_out, '-i', music_path,
            '-filter_complex', '[0:a][1:a]amix=inputs=2:weights=1 0.15[a]',
            '-map', '0:v', '-map', '[a]',
            '-c:v', 'copy', '-c:a', 'aac', '-shortest',
            final_out
        ], check=True)

        os.unlink(music_path)
        return send_file(final_out, mimetype='video/mp4',
                        as_attachment=True, download_name='reel.mp4')

    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
