"""Conservative view annotations. Never delete manuscript text or source anchors."""
import re
from collections import defaultdict


def annotate(doc):
    hidden=0
    folios=defaultdict(list)
    edge_folios=defaultdict(list)
    for page in doc.get('pages',[]):
        columns=defaultdict(list)
        for b in page['blocks']:
            b.pop('layout_ignored',None)
            if b.get('source_only'):continue
            box=b.get('bbox')
            if not box:continue
            text=b.get('text','').strip()
            # PDF extractors often combine a whole vertical run into one block.
            if re.fullmatch(r'\d{1,5}(?:\s+\d{1,5})*',text) and (box[2]<.09 or box[0]>.93):
                columns[round((box[0]+box[2])/2/.02)].append(b)
            if re.fullmatch(r'\d{1,5}',text):
                if box[3]<.10 or box[1]>.90:
                    edge_folios[(round((box[0]+box[2])/2/.02),round(box[1],2),int(text)-b['page'])].append(b)
                if (box[1]>.88 or box[3]<.07) and .35<(box[0]+box[2])/2<.65 and int(text)==b['page']+1:
                    folios[(round((box[0]+box[2])/2,2),round(box[1],2))].append(b)
                if box[3]<.045 or box[1]>.955:
                    b['layout_ignored']='页码'
                elif .91<box[0]<=.93:
                    columns[round((box[0]+box[2])/2/.02)].append(b)
        for group in columns.values():
            ordered=sorted(group,key=lambda b:b['bbox'][1])
            numbers=[int(n) for b in ordered for n in b['text'].split()]
            if len(numbers)<6 or ordered[-1]['bbox'][3]-ordered[0]['bbox'][1]<.18:continue
            steps=[b-a for a,b in zip(numbers,numbers[1:])]
            if sum(1<=step<=5 for step in steps)/len(steps)<.75:continue
            for b in ordered:b['layout_ignored']='审稿行号'
        hidden+=sum(bool(b.get('layout_ignored')) for b in page['blocks'])
    for group in [*folios.values(),*edge_folios.values()]:
        if len(group)>=2:
            for b in group:
                if not b.get('layout_ignored'):hidden+=1
                b['layout_ignored']='页码'
    doc['layout_cleanup']={'hidden_count':hidden}
    return doc
