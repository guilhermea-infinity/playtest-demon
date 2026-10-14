#!/usr/bin/env python3
"""Create a synthetic sample inbox for UI demos. Never calls an AI provider."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'mac'))
from desk_store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inbox', required=True, type=Path, help='New, empty directory only')
    args = parser.parse_args()
    root = args.inbox.expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        parser.error('Choose an empty directory; existing inboxes are never modified.')
    if not shutil.which('ffmpeg'):
        parser.error('ffmpeg is required to generate playable sample videos.')
    root.mkdir(parents=True, exist_ok=True)
    store = Store(root)
    store.configure({'paused': True})
    try:
        font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 22)
        large = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 38)
    except OSError:
        font = ImageFont.load_default(size=22)
        large = ImageFont.load_default(size=38)
    records = []
    for i, (game, status) in enumerate([('Pocket Garden', 'done'), ('Orbit Runner', 'working'), ('Pocket Garden', 'queued'), ('Tiny Workshop', 'failed')]):
        folder = root / game; folder.mkdir(exist_ok=True)
        clip = f'{game}/Demo {i+1:02d}.mp4'
        frame = Image.new('RGB', (360, 640), ['#e5eee1','#142b45','#e5eee1','#eadfd0'][i])
        d = ImageDraw.Draw(frame)
        ink = '#223628' if i != 1 else '#e8f1ff'
        d.text((24,30), game, font=large, fill=ink)
        d.rounded_rectangle((20,105,340,160),radius=15,fill='#ffffff' if i != 1 else '#294865')
        d.text((40,120),'Level 8       2,400 coins',font=font,fill=ink)
        for row in range(3):
            for col in range(3):
                x,y=32+col*106,206+row*97
                d.rounded_rectangle((x,y,x+82,y+78),radius=14,fill=['#9bbc80','#416d93','#a2bd90','#c69d76'][i])
                d.ellipse((x+25,y+18,x+57,y+50),fill=['#5e8d4a','#b8d8fc','#6f9859','#826544'][i])
        d.rounded_rectangle((38,528,322,590),radius=19,fill='#d4ac42')
        d.text((108,546),'Collect reward',font=font,fill='#263525')
        d.text((24,611),'Synthetic demo · QA Demon',font=font,fill=ink)
        preview = folder / f'demo-{i}.png';frame.save(preview)
        subprocess.run(['ffmpeg','-v','error','-y','-loop','1','-i',str(preview),'-t','3','-pix_fmt','yuv420p',str(root/clip)],check=True)
        meta={'file':clip,'app':game,'clipSeconds':3,'voice':False,'pressedAtSecond':1}
        records.append(meta)
        store.set_clip(clip, status=status, meta=meta, queuedAt=time.time()-i*60, tickets=[],
                       preview=str(preview.relative_to(root)), provider='codex' if i == 1 else 'claude', model='CLI default',
                       step='Codex is analysing' if status=='working' else None,
                       startedAt=time.time()-26 if status=='working' else None,
                       error='Example: model unavailable for this account. Choose another model and retry.' if status=='failed' else None,
                       summary='The reward button does not make its disabled state clear.' if status=='done' else None)
    clip=records[0]['file']
    for num,title in [(1,'Make the reward button’s disabled state clear'),(2,'Keep the coin total visible after collecting')]:
        store.save_ticket({'id':f'PG-{num:03d}','status':'draft','order':num,'game':'Pocket Garden','title':title,
                           'clip':clip,'frame':[360,640],'kind':'polish','priority':'normal','confidence':'high',
                           'where':'Garden screen, reward button at the bottom.',
                           'now':'The button stays yellow when there is no reward available.',
                           'want':'Dim the button and show when the next reward becomes available.',
                           'done_when':'An unavailable reward is visibly disabled and cannot be collected.',
                           'steps':[],'checks':[],'note':'','version':'Demo','clipSeconds':3,'pressedAtSecond':1,
                           'moment':{'from':0,'to':3},'quote':{'text':'Make it clear when I can collect the reward.','t':1},
                           'shots':[{'file':'Pocket Garden/demo-0.png','clean':'Pocket Garden/demo-0.png','t':1,'caption':'The reward action at the bottom of the garden.','use':True}]})
    (root/'inbox.jsonl').write_text(''.join(json.dumps(m)+'\n' for m in records))
    print(f'Synthetic inbox created at {root}. Launch QA Demon with --inbox "{root}" --no-inbox --paused.')

if __name__ == '__main__':
    main()
