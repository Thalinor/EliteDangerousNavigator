# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Assistant settings; draft edits stay local until Save or OK."""
from __future__ import annotations
import copy
import tkinter as tk
from tkinter import ttk, messagebox
import uuid
from .assistant import TOPICS, options, route
from .commands import validate, phrase_map

KINDS = {'Built In Chatbot':'builtin', 'Local Ollama':'ollama', 'OpenAI':'openai', 'OpenAI-compatible':'compatible'}


class AssistantPage:
    def __init__(self, manager, page):
        self.manager, self.app = manager, manager.app
        page.rowconfigure(0, weight=1)
        notebook = ttk.Notebook(page)
        notebook.grid(row=0, column=0, sticky='nsew')
        sections = {}
        for title in ('Behavior', 'AI Connections', 'Report Phrases'):
            frame = ttk.Frame(notebook, padding=8)
            frame.columnconfigure(1, weight=1)
            notebook.add(frame, text=title)
            sections[title] = frame
        self.vars = {}
        for key in ('reports_enabled','conversation_enabled','keyword_only','speak','use_frontier','share_context','allow_online'):
            self.vars[key] = tk.BooleanVar(page)
        for key in ('keyword', 'response_length'):
            self.vars[key] = tk.StringVar(page)
        self.aliases = tk.StringVar(page)
        self.ship_only = manager.ship_keyword_only
        body = sections['Behavior']
        ttk.Checkbutton(body, text='Enable local spoken reports', variable=self.vars['reports_enabled']).grid(row=0,column=0,sticky='w',pady=4)
        ttk.Checkbutton(body, text='Enable chatbot / conversational AI', variable=self.vars['conversation_enabled']).grid(row=0,column=1,sticky='w',pady=4)
        ttk.Checkbutton(body, text='Ship Inputs: Keyword Only', variable=self.ship_only).grid(row=1,column=0,sticky='w',pady=4)
        ttk.Entry(body, textvariable=manager.wake).grid(row=1,column=1,sticky='ew',pady=4)
        ttk.Checkbutton(body, text='Voice Assistant: Keyword Only', variable=self.vars['keyword_only']).grid(row=2,column=0,sticky='w',pady=4)
        ttk.Entry(body, textvariable=self.vars['keyword']).grid(row=2,column=1,sticky='ew',pady=4)
        ttk.Label(body,text='Other Assistant names (separate with ;)').grid(row=3,column=0,sticky='w',pady=4)
        ttk.Entry(body,textvariable=self.aliases).grid(row=3,column=1,sticky='ew',pady=4)
        ttk.Checkbutton(body,text='Speak Assistant replies',variable=self.vars['speak']).grid(row=4,column=0,sticky='w',pady=4)
        ttk.Combobox(body,textvariable=self.vars['response_length'],values=('Brief','Detailed'),state='readonly',width=15).grid(row=4,column=1,sticky='w',pady=4)
        for row,key,label in ((5,'use_frontier','Use Frontier account snapshots already received by EDMC'),
                              (6,'share_context','Share current system, ship and telemetry with selected AI'),
                              (7,'allow_online','Allow online AI requests (may use paid API credits)')):
            ttk.Checkbutton(body,text=label,variable=self.vars[key]).grid(row=row,column=0,columnspan=2,sticky='w',pady=4)
        ttk.Label(body,text='Local reports answer first. Both Keyword Only switches may be off; ambiguous phrases ask for clarification.\n'
                  'Frontier data uses EDMC authorization, never adds requests. AI receives only your question unless sharing is enabled.',
                  wraplength=730).grid(row=8,column=0,columnspan=2,sticky='w',pady=7)
        ask = ttk.Frame(body); ask.grid(row=9,column=0,columnspan=2,sticky='ew',pady=4)
        ask.columnconfigure(0,weight=1)
        self.question = tk.StringVar(page)
        entry = ttk.Entry(ask,textvariable=self.question); entry.grid(row=0,column=0,sticky='ew')
        entry.bind('<Return>',lambda _:self.ask())
        ttk.Button(ask,text='Ask (saved settings)',command=self.ask).grid(row=0,column=1,padx=4)
        ttk.Button(ask,text='Try Routing (no actions)',command=self.try_route).grid(row=0,column=2)
        body.rowconfigure(10,weight=1)
        self.answer = tk.Text(body,width=1,height=4,wrap='word',state='disabled',takefocus=True)
        self.answer.grid(row=10,column=0,columnspan=2,sticky='nsew',pady=4)

        body = sections['AI Connections']
        self.connection = tk.StringVar(page)
        self.connection_box = ttk.Combobox(body,textvariable=self.connection,state='readonly')
        self.connection_box.grid(row=0,column=0,columnspan=2,sticky='ew',pady=4)
        self.connection_box.bind('<<ComboboxSelected>>', self.select_profile)
        actions = ttk.Frame(body); actions.grid(row=1,column=0,columnspan=2,sticky='w',pady=4)
        for label,command in (('Add Connection',self.add_profile),('Remove Connection',self.remove_profile)):
            ttk.Button(actions,text=label,command=command).pack(side='left',padx=(0,6))
        self.fields = {k:tk.StringVar(page) for k in ('name','kind','endpoint','model')}
        self.field_widgets = {}
        for row,key,label in ((2,'name','Connection name'),(3,'kind','Connection type'),
                              (4,'endpoint','Server address'),(5,'model','Model name')):
            ttk.Label(body,text=label).grid(row=row,column=0,sticky='w',padx=(0,12),pady=5)
            if key=='kind':
                widget=ttk.Combobox(body,textvariable=self.fields[key],values=tuple(k for k,v in KINDS.items() if v!='builtin'),state='readonly')
                widget.bind('<<ComboboxSelected>>',self.kind_changed)
            else:
                widget=ttk.Entry(body,textvariable=self.fields[key])
            widget.grid(row=row,column=1,sticky='ew',pady=5)
            self.field_widgets[key] = widget
        self.key = tk.StringVar(page)
        ttk.Label(body,text='API key (stored separately in Windows)').grid(row=6,column=0,sticky='w',padx=(0,12),pady=5)
        self.key_entry = ttk.Entry(body,textvariable=self.key,show='*')
        self.key_entry.grid(row=6,column=1,sticky='ew',pady=5)
        actions = ttk.Frame(body); actions.grid(row=7,column=0,columnspan=2,sticky='w',pady=5)
        self.key_buttons = []
        for label,command in (('Save Key',self.save_key),('Remove Key',self.remove_key),
                              ('Test AI (may use credits)',self.test_connection)):
            button = ttk.Button(actions,text=label,command=command)
            button.pack(side='left',padx=(0,6))
            self.key_buttons.append(button)
        self.key_status = tk.StringVar(page)
        ttk.Label(body,textvariable=self.key_status,wraplength=730).grid(row=8,column=0,columnspan=2,sticky='w',pady=6)
        ttk.Label(body,text='Built In Chatbot uses local game/plugin data, without an AI model, API key or connection.\n'
                  'For other connections, enter the exact model name available on your server/account. Nothing downloads automatically.\n'
                  'OpenAI uses its Responses API. Compatible connections use Chat Completions; provider support varies.\n'
                  'Keys save separately from this form and are excluded from backups. Remove Key before removing a connection.\n'
                  'Opening settings makes no network requests. Tests send a small prompt, without game data.',
                  wraplength=730).grid(row=9,column=0,columnspan=2,sticky='w',pady=8)

        body = sections['Report Phrases']; body.columnconfigure(0,weight=1); body.rowconfigure(0,weight=1)
        self.table = ttk.Treeview(body,columns=('phrase','topic'),show='headings',selectmode='browse',height=7)
        self.table.heading('phrase',text='Spoken question (without keyword)'); self.table.heading('topic',text='Local report')
        self.table.column('phrase',width=470);self.table.column('topic',width=170)
        self.table.grid(row=0,column=0,columnspan=2,sticky='nsew')
        bar=ttk.Scrollbar(body,orient='vertical',command=self.table.yview);bar.grid(row=0,column=2,sticky='ns')
        self.table.configure(yscrollcommand=bar.set)
        self.phrase,self.topic = tk.StringVar(page),tk.StringVar(page,value=TOPICS['fuel'])
        ttk.Entry(body,textvariable=self.phrase).grid(row=1,column=0,sticky='ew',pady=6)
        ttk.Combobox(body,textvariable=self.topic,values=tuple(TOPICS.values()),state='readonly').grid(row=1,column=1,pady=6,padx=5)
        actions = ttk.Frame(body);actions.grid(row=2,column=0,columnspan=2,sticky='w')
        ttk.Button(actions,text='Add Phrase',command=self.add_query).pack(side='left',padx=(0,6))
        ttk.Button(actions,text='Remove Selected',command=self.remove_query).pack(side='left')
        ttk.Label(body,text='These phrases are recognized locally. Add another wording for a report, or remove phrases you do not use.\n'
                  'Reports never query an AI service or community website. Voice requests use the configured Assistant keyword.',
                  wraplength=730).grid(row=3,column=0,columnspan=2,sticky='w',pady=10)
        footer=ttk.Frame(page);footer.grid(row=1,column=0,sticky='ew',pady=(8,0))
        ttk.Button(footer,text='Save Assistant Settings',command=self.save).pack(side='left')
        ttk.Button(footer,text='Cancel',command=manager.destroy).pack(side='right')
        ttk.Button(footer,text='OK',command=lambda:self.save(close=True)).pack(side='right',padx=6)
        self.reload()

    def reload(self):
        self.draft = options(self.app.settings)
        for k,v in self.vars.items(): v.set(self.draft[k])
        self.aliases.set('; '.join(self.draft['aliases']))
        self.ship_only.set(self.app.settings.get('ship_keyword_only',bool(self.app.settings.get('wake_word','').strip())))
        self.profiles = copy.deepcopy(self.draft['profiles'])
        self.selected = self.draft['active_profile']
        self.profile_list()
        self.load_profile()
        self.refresh_queries()
        self.set_answer(self.app.assistant_answer or 'Assistant is optional. Enable local reports, conversational AI, or both, then Save.')

    def profile_list(self):
        self.ids=[p['id'] for p in self.profiles]
        self.names=['{} — {}'.format(n+1,p['name']) for n,p in enumerate(self.profiles)]
        self.connection_box.configure(values=self.names)
        self.connection.set(self.names[self.ids.index(self.selected)])

    def profile(self):
        return next(p for p in self.profiles if p['id']==self.selected)

    def commit_profile(self):
        if self.profile()['kind']=='builtin':return
        self.profile().update(name=self.fields['name'].get().strip(),
            kind=KINDS[self.fields['kind'].get()],endpoint=self.fields['endpoint'].get().strip().rstrip('/'),
            model=self.fields['model'].get().strip())

    def load_profile(self):
        profile=self.profile()
        for key,var in self.fields.items():
            var.set(next(label for label,kind in KINDS.items() if kind==profile[key]) if key=='kind' else profile[key])
        self.key.set('')
        builtin=profile['kind']=='builtin'
        for name,widget in self.field_widgets.items():
            widget.configure(state='disabled' if builtin else 'readonly' if name=='kind' else 'normal')
        self.key_entry.configure(state='disabled' if builtin else 'normal')
        for button in self.key_buttons[:2]:button.configure(state='disabled' if builtin else 'normal')
        self.key_buttons[2].configure(text='Test Chatbot' if builtin else 'Test AI (may use credits)')
        self.key_status.set('Built In Chatbot is offline and needs no key.' if builtin else
            'Keys save only when you press Save Key; they are not included in portable backups.')

    def select_profile(self,event=None):
        chosen=self.ids[self.connection_box.current()]
        self.commit_profile();self.selected=chosen
        self.profile_list();self.load_profile()

    def kind_changed(self,event=None):
        kind=KINDS[self.fields['kind'].get()]
        self.fields['endpoint'].set({'ollama':'http://127.0.0.1:11434',
            'openai':'https://api.openai.com/v1','compatible':'http://127.0.0.1:1234/v1'}[kind])

    def add_profile(self):
        self.commit_profile()
        self.selected=uuid.uuid4().hex
        self.profiles.append(dict(id=self.selected,name='New connection',kind='compatible',
                                  endpoint='http://127.0.0.1:1234/v1',model=''))
        self.profile_list();self.load_profile()

    def remove_profile(self):
        if self.profile()['kind']=='builtin':
            self.error('Built In Chatbot stays available. Select a removable connection instead.');return
        if len(self.profiles)<=1:
            self.error('Keep at least one connection. Conversational AI can remain disabled.');return
        self.profiles=[p for p in self.profiles if p['id']!=self.selected]
        self.selected=self.profiles[0]['id'];self.profile_list();self.load_profile()

    def refresh_queries(self):
        self.table.delete(*self.table.get_children())
        for n,q in enumerate(self.draft['queries']):
            self.table.insert('', 'end', iid=str(n),values=(q['phrase'],TOPICS[q['topic']]))

    def add_query(self):
        phrase=self.phrase.get().strip()
        if not phrase:return
        self.draft['queries'].append(dict(phrase=phrase,topic=next(k for k,v in TOPICS.items() if v==self.topic.get())))
        self.refresh_queries();self.phrase.set('')

    def remove_query(self):
        selected=self.table.selection()
        if selected:
            self.draft['queries'].pop(int(selected[0]));self.refresh_queries()

    def candidate(self):
        self.commit_profile()
        opts=copy.deepcopy(self.draft)
        opts.update({k:v.get() for k,v in self.vars.items()})
        opts.update(aliases=[w.strip() for w in self.aliases.get().split(';') if w.strip()],
                    profiles=copy.deepcopy(self.profiles),active_profile=self.selected)
        settings=copy.deepcopy(self.app.settings)
        settings.update(assistant_settings=opts,wake_word=self.manager.wake.get().strip(),ship_keyword_only=self.ship_only.get())
        return validate(settings)

    def error(self,text):
        messagebox.showerror('(N) Voice Assistant',str(text),parent=self.manager)

    def save(self,close=False):
        try:
            self.app.apply_settings(self.candidate())
            self.app.log('Assistant settings saved')
            if close:self.manager.destroy()
        except (ValueError,OSError,tk.TclError) as error:self.error(error)

    def save_key(self):
        try:
            self.candidate()
            self.app.ai.keys.write(self.profile(),self.key.get().strip())
            self.key.set('');self.key_status.set('Key saved in Windows Credential Manager for this connection address.')
        except (ValueError,OSError) as error:self.error(error)

    def remove_key(self):
        try:
            self.candidate();self.app.ai.keys.remove(self.profile())
            self.key.set('');self.key_status.set('Saved key removed for this connection address.')
        except (ValueError,OSError) as error:self.error(error)

    def test_connection(self):
        try:self.app.ask_assistant('',test=True,candidate=self.candidate())
        except (ValueError,OSError) as error:self.error(error)

    def try_route(self):
        try:
            settings=self.candidate()
            kind,value=route(self.question.get(),settings,phrase_map(settings))
            self.set_answer('Route: '+kind+(' — '+value['name'] if kind=='macro' else ' — '+str(value)))
        except (ValueError,OSError) as error:self.error(error)

    def ask(self):
        question=self.question.get().strip()
        if question:
            kind,value=route(question,self.app.settings,{})
            self.app.ask_assistant(value if kind=='assistant' else question)

    def set_answer(self,text):
        if self.answer.get('1.0','end-1c')!=text:
            self.answer.configure(state='normal');self.answer.delete('1.0','end')
            self.answer.insert('1.0',text);self.answer.configure(state='disabled')
