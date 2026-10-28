import copy
import json
import unittest
import context_manager as cm
import writing


def document():
    texts=[('heading','1 Introduction'),('paragraph','We introduce the acoustic codec for speech compression.'),
           ('heading','2 Methods'),('paragraph','The acoustic codec uses residual quantization and 24 channels.'),
           ('paragraph','We evaluate the proposed model on held-out speech.'),
           ('heading','3 Results'),('paragraph','Residual quantization achieves 93.5% accuracy on speech with 24 channels.'),
           ('paragraph','The unrelated image baseline uses spatial patch augmentation.')]
    return {'id':'paper','pages':[{'blocks':[{'id':f'b{i}','page':i//4,'text':t,'kind':k} for i,(k,t) in enumerate(texts)]}], 'annotations':[]}


class ContextTests(unittest.TestCase):
    def test_retrieval_provenance_and_no_mutation(self):
        doc=document();old=copy.deepcopy(doc);b=doc['pages'][0]['blocks'][3]
        package=cm.build(doc,b,{'instruction':'Explain residual quantization accuracy'}, {},lambda _:None)
        self.assertIn('b6',[r['block_id'] for r in package['evidence']])
        for row in package['evidence']:
            source=next(b for b in doc['pages'][0]['blocks'] if b['id']==row['block_id'])
            self.assertEqual(source['text'][row['start']:row['end']],row['text'])
        self.assertLessEqual(package['estimated_input_tokens'],package['budget'])
        self.assertEqual(doc,old)

    def test_exclusion_removes_summary_and_source(self):
        doc=document();b=doc['pages'][0]['blocks'][3]
        _,units=cm.index(doc);store={cm.cache_key(u,{}):{'summary':'OLD SUMMARY','terms':[],'claims':[]} for u in units}
        p=cm.build(doc,b,{'context_options':{'excludes':['b6']}}, {},store.get)
        self.assertNotIn('b6',[r['block_id'] for r in p['evidence']])
        result=next(o for o in p['overview'] if o['section']=='3 Results')
        self.assertNotIn('OLD SUMMARY',result['text'])
        self.assertNotIn('93.5',json.dumps(result))

    def test_incremental_cache_across_recompilation_and_model(self):
        doc=document();_,before=cm.index(doc)
        copy_doc=copy.deepcopy(doc)
        for b in copy_doc['pages'][0]['blocks']:b['id']='new-'+b['id'];b['page']+=1
        _,renumbered=cm.index(copy_doc)
        self.assertEqual([cm.cache_key(u,{}) for u in before],[cm.cache_key(u,{}) for u in renumbered])
        copy_doc['pages'][0]['blocks'][6]['text']+=' New limitation.'
        _,after=cm.index(copy_doc)
        self.assertEqual([u['hash'] for u in before[:2]],[u['hash'] for u in after[:2]])
        self.assertNotEqual(before[-1]['hash'],after[-1]['hash'])
        self.assertNotEqual(cm.cache_key(before[0],{'model':'a'}),cm.cache_key(before[0],{'model':'b'}))

    def test_pin_overflow_and_target_exclusion_are_explicit(self):
        doc=document();b=doc['pages'][0]['blocks'][3]
        doc['pages'][0]['blocks'][7]['text']='Long evidence. '*2500
        with self.assertRaisesRegex(ValueError,'固定段落超出预算'):
            cm.build(doc,b,{'context_options':{'budget':4000,'pins':['b7']}},{},lambda _:None)
        with self.assertRaisesRegex(ValueError,'当前选区'):
            cm.build(doc,b,{'context_options':{'excludes':['b3']}},{},lambda _:None)

    def test_prompt_is_bounded_and_context_saved(self):
        doc=document();b=doc['pages'][0]['blocks'][3]
        a={'start':0,'end':len(b['text']),'quote':b['text'],'instruction':'Tighten the sentence.'}
        package=cm.build(doc,b,a,{},lambda _:None);a['context_package']=package
        calls=[]
        def complete(messages,config):
            calls.append(messages)
            return json.dumps({'replacement':b['text'],'translation':'译文','rationale':'理由'})
        proposal=writing.build_proposal(doc,b,a,{'model':'mock'},complete)
        self.assertEqual(proposal['context'],package)
        payload=json.loads(calls[0][1]['content'])
        self.assertEqual(payload['target'],b['text'])
        self.assertLessEqual(cm.estimate(json.dumps(calls[0],ensure_ascii=False)),package['budget'])
        self.assertIn('TARGET ONLY',calls[0][0]['content'])

    def test_fingerprint_changes_with_source_and_policy(self):
        doc=document();b=doc['pages'][0]['blocks'][3]
        one=cm.build(doc,b,{}, {},lambda _:None)
        two=cm.build(doc,b,{'context_options':{'constraints':'Avoid claims of superiority.'}}, {},lambda _:None)
        self.assertNotEqual(one['fingerprint'],two['fingerprint'])
        doc['pages'][0]['blocks'][6]['text']='Changed result.'
        three=cm.build(doc,b,{}, {},lambda _:None)
        self.assertNotEqual(one['revision'],three['revision'])

    def test_whole_paper_overview_is_invalidated_with_any_changed_section(self):
        doc=document();b=doc['pages'][0]['blocks'][3];_,units=cm.index(doc)
        store={cm.cache_key(u,{}):{'summary':'Section summary','terms':[],'claims':[]} for u in units}
        whole=cm.overview_unit(units,{},store.get)
        store[cm.cache_key(whole,{})]={'summary':'Whole paper summary','terms':[],'claims':[]}
        p=cm.build(doc,b,{}, {},store.get)
        self.assertEqual(p['overview'][0]['text'],'Whole paper summary')
        self.assertEqual(p['overview_coverage'],{'included':3,'total':3})
        doc['pages'][0]['blocks'][6]['text']='Changed result.'
        p=cm.build(doc,b,{}, {},store.get)
        self.assertNotIn('Whole paper summary',json.dumps(p))

    def test_dense_manuscript_respects_all_budgets(self):
        doc=document();b=doc['pages'][0]['blocks'][3]
        for n in range(60):doc['pages'][0]['blocks'].append({'id':str(n),'page':9,'kind':'paragraph','text':('Acoustic codec speech accuracy, with uncertainty. '*30)+str(n)})
        for budget in (4000,8000,16000):
            p=cm.build(doc,b,{'context_options':{'budget':budget}},{},lambda _:None)
            self.assertLessEqual(p['estimated_input_tokens'],budget)


if __name__=='__main__':unittest.main()
