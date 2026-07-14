import json
b=json.load(open('command_registry/local_discovery.json',encoding='utf-8'))
deep=[{'id':'plumbing_xxgl','domain':'plumbing','primary_command':'xxgl','matched_in':['tmn_partial']},
      {'id':'plumbing_gxlj','domain':'plumbing','primary_command':'gxlj','matched_in':['tmn_partial']},
      {'id':'plumbing_dggj','domain':'plumbing','primary_command':'dggj','matched_in':['tmn_partial']},
      {'id':'plumbing_tsaveas','domain':'plumbing','primary_command':'TSaveAs','matched_in':['tmn']}]
existing={d['id'] for d in b['discovered']}
added=[d for d in deep if d['id'] not in existing]
b['discovered'].extend(added)
b['total_discovered']=len(b['discovered'])
b['by_domain']['plumbing']=sum(1 for d in b['discovered'] if d['domain']=='plumbing')
b['by_domain']['hvac']=sum(1 for d in b['discovered'] if d['domain']=='hvac')
json.dump(b,open('command_registry/local_discovery.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)
print('MERGED total:',b['total_discovered'],'P:',b['by_domain']['plumbing'],'H:',b['by_domain']['hvac'])
for d in b['discovered']:
    print('  [%s] %s: %s <- %s' % (d['domain'],d['id'],d['primary_command'],d['matched_in']))
