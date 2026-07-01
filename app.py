from flask import Flask, request, jsonify
import subprocess, os, requests, tempfile, uuid, threading

app = Flask(__name__)

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
        text = scene['text']
        out = f'/tmp/scene_{i}.mp4'
        
        cmd = [
            'ffmpeg', '-y',
            '-loop', '1', '-i', img_path,
            '-i', audio_path,
            '-vf', f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,zoompan=z='min(zoom+0.001,1.1)':d=1:s=1080x1920,drawtext=text='{text}':fontcolor=white:fontsize=50:x=(w-text_w)/2:y=(h-text_h)/2:shadowcolor=black:shadowx=2:shadowy=2,drawtext=text='{channel_name}':fontcolor=white:fontsize=30:x=(w-text_w)/2:y=h-80:shadowcolor=black:shadowx=2:shadowy=2,colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
            '-shortest', '-c:v', 'libx264', '-c:a', 'aac',
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
    subprocess.run(['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', list_file, '-c', 'copy', concat_out], check=True)
    
    final_out = f'/tmp/final_{uuid.uuid4().hex}.mp4'
    subprocess.run([
        'ffmpeg', '-y', '-i', concat_out, '-i', music_path,
        '-filter_complex', '[0:a][1:a]amix=inputs=2:weights=1 0.15[a]',
        '-map', '0:v', '-map', '[a]',
        '-c:v', 'copy', '-c:a', 'aac', '-shortest',
        final_out
    ], check=True)
    
    os.unlink(music_path)
    
    with open(final_out, 'rb') as f:
        video_data = f.read()
    
    os.unlink(final_out)
    
    return jsonify({'status': 'done', 'size': len(video_data)}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
