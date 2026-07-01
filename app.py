from flask import Flask, request, jsonify, send_file
import subprocess, os, requests, tempfile, uuid
import imageio_ffmpeg

app = Flask(__name__)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

def download_file(url, suffix):
    r = requests.get(url)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(r.content)
    tmp.close()
    return tmp.name

@app.route('/render', methods=['POST'])
def render():
    data = request.json
    scenes = data['scenes']
    music_url = data['music_url']
    channel_name = data.get('channel_name', 'My Channel')
    
    music_path = download_file(music_url, '.mp3')
    scene_videos = []
    
    for i, scene in enumerate(scenes):
        img_path = download_file(scene['image_url'], '.jpg')
        audio_path = download_file(scene['audio_url'], '.mp3')
        text = scene['text'].replace("'", "\\'")
        out = f'/tmp/scene_{i}.mp4'
        
        cmd = [
            FFMPEG, '-y',
            '-loop', '1', '-i', img_path,
            '-i', audio_path,
            '-vf', f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,drawtext=text='{text}':fontcolor=white:fontsize=45:x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black:shadowx=2:shadowy=2,drawtext=text='{channel_name}':fontcolor=white:fontsize=28:x=(w-text_w)/2:y=h-70:shadowcolor=black:shadowx=2:shadowy=2",
            '-shortest', '-c:v', 'libx264', '-c:a', 'aac', '-pix_fmt', 'yuv420p',
            out
        ]
        subprocess.run(cmd, check=True)
        scene_videos.append(out)
        os.unlink(img_path)
        os.unlink(audio_path)
    
    list_file = '/tmp/list.txt'
    with open(list_file, 'w') as f:
        for v in scene_videos:
            f.write(f"file '{v}'\n")
    
    concat_out = '/tmp/concat.mp4'
    subprocess.run([FFMPEG, '-y', '-f', 'concat', '-safe', '0', '-i', list_file, '-c', 'copy', concat_out], check=True)
    
    final_out = f'/tmp/final_{uuid.uuid4().hex}.mp4'
    subprocess.run([
        FFMPEG, '-y', '-i', concat_out, '-i', music_path,
        '-filter_complex', '[0:a][1:a]amix=inputs=2:weights=1 0.15[a]',
        '-map', '0:v', '-map', '[a]',
        '-c:v', 'copy', '-c:a', 'aac', '-shortest',
        final_out
    ], check=True)
    
    os.unlink(music_path)
    
    return send_file(final_out, mimetype='video/mp4', as_attachment=True, download_name='reel.mp4')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
