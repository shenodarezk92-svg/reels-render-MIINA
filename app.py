from flask import Flask, request, jsonify, send_file
import subprocess, os, requests, tempfile, uuid, traceback
import imageio_ffmpeg

app = Flask(__name__)
@app.route('/health', methods=['GET'])
def health():
    return {'status': 'alive'}, 200

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

def download_file(url, suffix):
    r = requests.get(url, timeout=30)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(r.content)
    tmp.close()
    return tmp.name

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
            text = scene['text'].replace("'", "").replace('"', '')
            out = f'/tmp/scene_{i}.mp4'

            # تم تقليل الدقة من 1080x1920 إلى 720x1280 لتقليل استهلاك الرام
            cmd = [
                FFMPEG, '-y',
                '-loop', '1', '-i', img_path,
                '-i', audio_path,
                '-vf', f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,drawtext=text='{text}':fontcolor=white:fontsize=32:x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black:shadowx=2:shadowy=2,drawtext=text='{channel_name}':fontcolor=white:fontsize=20:x=(w-text_w)/2:y=h-50:shadowcolor=black:shadowx=2:shadowy=2",
                '-shortest',
                '-c:v', 'libx264',
                '-preset', 'veryfast',   # تقليل استهلاك الرام والمعالجة أثناء الـ encoding
                '-c:a', 'aac',
                '-pix_fmt', 'yuv420p',
                out
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return jsonify({'error': result.stderr}), 500

            scene_videos.append(out)
            os.unlink(img_path)
            os.unlink(audio_path)

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

        # تنظيف ملفات المشاهد المؤقتة بعد الانتهاء لتفريغ المساحة والرام
        for v in scene_videos:
            if os.path.exists(v):
                os.unlink(v)
        if os.path.exists(concat_out):
            os.unlink(concat_out)
        if os.path.exists(list_file):
            os.unlink(list_file)

        return send_file(final_out, mimetype='video/mp4',
                        as_attachment=True, download_name='reel.mp4')

    except Exception as e:
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
