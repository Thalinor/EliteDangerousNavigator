# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Standard scrollable EDMC preferences; changes commit through Apply/OK."""
from __future__ import annotations

import copy
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

import myNotebook as nb


class RadioSettings:
    def __init__(self,parent,api):
        self.api=api
        self.library=copy.deepcopy(api._library)
        self.closed=False
        self.preview=None
        self.preview_job=None
        self.preview_busy=False
        self.preview_task=''
        self.voices=['Windows Default']
        try:
            from plug import invoke
            self.frame=invoke('(N) Interface','Navigator Interface','navigator_scroll_settings',parent,570,440)
            self.body=getattr(self.frame,'navigator_settings_content',None)
        except ImportError:
            self.frame=None
            self.body=None
        if self.body is None:
            self.frame=nb.Frame(parent)
            self.body=self.frame
        self.body.columnconfigure(0,weight=1)
        self.frame.bind('<Destroy>',self._destroy,add='+')
        ttk.Label(self.body,text=f'{api.TITLE} {api.VERSION}').grid(row=0,column=0,sticky='w',padx=10,pady=8)
        local=self.section('Local Music',2)
        self.folders=self.tree(local,('station','path','tracks'),('Station','Folder Path','Tracks'),(120,285,90))
        bar=ttk.Frame(local);bar.grid(row=1,column=0,sticky='w',pady=5)
        for text,command in [('Add Folder…',self.add_folder),('Remove Selected',self.remove_folders),('Rescan Selected',self.rescan)]:
            ttk.Button(bar,text=text,command=command).pack(side='left',padx=(0,5))
        ttk.Label(local,text='Each folder and its subfolders form one station. Removing an entry never deletes files.',wraplength=500).grid(row=2,column=0,sticky='w')
        streams=self.section('Internet Radio',3)
        self.filter=tk.StringVar(self.frame)
        ttk.Label(streams,text='Filter Stations:').grid(row=0,column=0,sticky='w')
        entry=ttk.Entry(streams,textvariable=self.filter)
        entry.grid(row=1,column=0,sticky='ew',pady=(0,4))
        self.streams=self.tree(streams,('playlist','station'),('Playlist','Station'),(175,315),row=2)
        self.filter.trace_add('write',lambda *a:self.refresh_streams())
        bar=ttk.Frame(streams);bar.grid(row=3,column=0,sticky='w',pady=5)
        for text,command in [('Import Playlist…',self.import_playlist),('Add Link…',self.add_link),('Rename…',self.rename_stream),('Remove Selected',self.remove_streams)]:
            ttk.Button(bar,text=text,command=command).pack(side='left',padx=(0,5))
        ttk.Label(streams,text='Previous/Next: station within playlist. Up/Down: playlist. Re-import old playlists to restore their groups.',wraplength=500).grid(row=5,column=0,sticky='w',pady=4)
        self.vars={}
        self.check(streams,'data_saver','Distant Radio: Use Data Saver Streams',4)
        voice=self.section('Galnet Voice',4)
        voice.columnconfigure(1,weight=1)
        ttk.Label(voice,text='Voice:').grid(row=0,column=0,sticky='w')
        self.voice=tk.StringVar(self.frame,value=api._settings['voice'] or 'Windows Default')
        self.voice_box=ttk.Combobox(voice,textvariable=self.voice,values=self.voices,state='readonly')
        self.voice_box.grid(row=0,column=1,sticky='ew',padx=(8,0))
        self.slider(voice,'voice_rate','Speaking Speed:',-10,10,1)
        self.slider(voice,'voice_pitch','Pitch (%):',-50,50,2)
        self.slider(voice,'voice_volume','Voice Volume (%):',0,100,3)
        ttk.Label(voice,text='0 = Normal speed/pitch. Pitch response depends on the selected Windows voice.',wraplength=500).grid(row=4,column=0,columnspan=3,sticky='w',pady=4)
        bar=ttk.Frame(voice);bar.grid(row=5,column=0,columnspan=3,sticky='w',pady=5)
        for text,command in [('Preview Voice',self.preview_voice),('Stop Preview',self.stop_preview),('Reset Voice Defaults',self.reset_voice)]:
            ttk.Button(bar,text=text,command=command).pack(side='left',padx=(0,5))
        self.voice_status=ttk.Label(voice,text='Windows Default is available. Load Voices to list other installed voices.',wraplength=500)
        self.voice_status.grid(row=6,column=0,columnspan=3,sticky='w')
        ttk.Button(voice,text='Refresh Voices',command=self.load_voices).grid(row=7,column=0,columnspan=3,sticky='w',pady=4)
        self.check(voice,'galnet_unread','Play Only Unread Galnet Articles',8,span=3)
        # Suite settings order: everyday options first (Playback), then sources, then About.
        playback=self.section('Playback',1)
        playback.columnconfigure(1,weight=1)
        self.slider(playback,'volume','Radio / Music Volume (%):',0,100,0)
        self.check(playback,'autoplay','Start Playing When EDMC Starts',1,span=3)
        self.check(playback,'pause_on_shutdown','Pause When The Game Shuts Down',2,span=3)
        self.check(playback,'resume_music','Remember Local Music Track And Position',3,span=3)
        ttk.Label(playback,text='Remembering a position never starts playback by itself. Repeat and Shuffle use the panel icons.',wraplength=500).grid(row=4,column=0,columnspan=3,sticky='w',pady=5)
        ttk.Button(self.body,text='About '+api.TITLE,command=lambda:messagebox.showinfo(api.TITLE,api.ABOUT_TEXT,parent=self.frame)).grid(row=5,column=0,sticky='w',padx=10,pady=8)
        self.refresh_folders();self.refresh_streams()
        for item in self.library['folders']:
            if api._folder_key(item['path']) not in api._music_cache:api._request_music_scan(item['path'])
        self.load_voices()

    def alive(self):
        return not self.closed and bool(self.frame.winfo_exists())

    def section(self,title,row):
        frame=ttk.LabelFrame(self.body,text=title,padding=8)
        frame.grid(row=row,column=0,sticky='ew',padx=10,pady=5)
        frame.columnconfigure(0,weight=1)
        return frame

    def tree(self,parent,columns,headings,widths,row=0):
        frame=ttk.Frame(parent);frame.grid(row=row,column=0,sticky='ew')
        frame.columnconfigure(0,weight=1)
        tree=ttk.Treeview(frame,columns=columns,show='headings',height=4,selectmode='extended')
        tree.grid(row=0,column=0,sticky='nsew')
        vertical=ttk.Scrollbar(frame,orient='vertical',command=tree.yview)
        vertical.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(frame,orient='horizontal',command=tree.xview)
        horizontal.grid(row=1,column=0,sticky='ew')
        tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set)
        for column,title,width in zip(columns,headings,widths):
            tree.heading(column,text=title)
            tree.column(column,width=width,minwidth=60,stretch=column=='path' or len(columns)==1)
        return tree

    def check(self,parent,key,text,row,span=1):
        var=tk.BooleanVar(self.frame,value=bool(self.api._settings[key]));self.vars[key]=var
        ttk.Checkbutton(parent,text=text,variable=var).grid(row=row,column=0,columnspan=span,sticky='w',pady=3)

    def slider(self,parent,key,title,low,high,row):
        var=tk.IntVar(self.frame,value=int(self.api._settings[key]));self.vars[key]=var
        ttk.Label(parent,text=title).grid(row=row,column=0,sticky='w')
        tk.Scale(parent,from_=low,to=high,resolution=1,orient='horizontal',variable=var,
                 showvalue=False,highlightthickness=0).grid(row=row,column=1,sticky='ew',padx=8)
        ttk.Label(parent,textvariable=var,width=4,anchor='e').grid(row=row,column=2,sticky='e')

    def refresh_folders(self):
        selected=self.folders.selection();self.folders.delete(*self.folders.get_children())
        for i,item in enumerate(self.library['folders']):
            path=item['path'];key=self.api._folder_key(path);cached=self.api._music_cache.get(key)
            count='Scanning…' if key in self.api._music_pending else (cached.get('error') or str(len(cached['tracks']))) if cached else 'Not Scanned'
            self.folders.insert('', 'end',iid=str(i),values=(os.path.basename(os.path.normpath(path)) or path,path,count))
        for i in selected:
            if self.folders.exists(i):self.folders.selection_add(i)

    def refresh_streams(self):
        self.streams.delete(*self.streams.get_children())
        query=self.filter.get().casefold()
        for i,item in enumerate(self.library['streams']):
            group=self.api.stream_groups.group_name(item)
            if query in (group+' '+item['name']).casefold():self.streams.insert('','end',iid=str(i),values=(group,item['name']))

    def add_folder(self):
        path=filedialog.askdirectory(parent=self.frame,title='Add Music Folder',mustexist=True)
        if not path:return
        path=os.path.normpath(path);key=self.api._folder_key(path)
        if any(self.api._folder_key(i['path'])==key for i in self.library['folders']):return
        self.library['folders'].append({'name':os.path.basename(path) or path,'path':path})
        self.api._request_music_scan(path);self.refresh_folders()

    def remove_folders(self):
        for i in sorted(map(int,self.folders.selection()),reverse=True):del self.library['folders'][i]
        self.refresh_folders()

    def rescan(self):
        for i in self.folders.selection():self.api._request_music_scan(self.library['folders'][int(i)]['path'],force=True)
        self.refresh_folders()

    def import_playlist(self):
        path=filedialog.askopenfilename(parent=self.frame,title='Import Internet Radio Playlist',filetypes=[('Playlists','*.pls *.m3u *.m3u8'),('All Files','*.*')])
        if not path:return
        try:items=self.api.sources.read_playlist_file(path)
        except (OSError,ValueError):
            messagebox.showerror(api.TITLE,'Could not read that playlist.',parent=self.frame);return
        self.api.stream_groups.import_playlist(self.library,path,items)
        self.refresh_streams()

    def add_link(self):
        url=simpledialog.askstring(api.TITLE,'Stream Link (http:// or https://):',parent=self.frame)
        if not url:return
        url=url.strip()
        if not url.lower().startswith(('http://','https://')):
            messagebox.showerror(api.TITLE,'Please enter an HTTP or HTTPS stream link.',parent=self.frame);return
        name=simpledialog.askstring(api.TITLE,'Station Name:',parent=self.frame)
        if not name:return
        if not any(i['url']==url and self.api.stream_groups.group_name(i)==self.api.stream_groups.CUSTOM for i in self.library['streams']):
            self.library['streams'].append({'name':name.strip() or 'Stream','url':url,'playlist':self.api.stream_groups.CUSTOM})
        self.refresh_streams()

    def remove_streams(self):
        for i in sorted(map(int,self.streams.selection()),reverse=True):del self.library['streams'][i]
        self.refresh_streams()

    def rename_stream(self):
        selected=self.streams.selection()
        if len(selected)!=1:return
        item=self.library['streams'][int(selected[0])]
        name=simpledialog.askstring(api.TITLE,'Station Name:',initialvalue=item['name'],parent=self.frame)
        if name and name.strip():item['name']=name.strip();self.refresh_streams()

    def _start_preview_helper(self):
        if self.preview is None:self.preview=self.api.Engine()
        if not self.api.Engine.available():self.voice_status.configure(text='Windows speech is unavailable.');return False
        return True

    def load_voices(self):
        if self._start_preview_helper():
            self.preview_busy=True
            self.preview_task='voices'
            if not self.preview.send('voices'):self.preview_busy=False
            self.voice_status.configure(text='Loading Installed Voices…');self._poll_preview()

    def preview_voice(self):
        if self._start_preview_helper():
            self.preview_busy=True
            self.preview_task='speaking'
            ok=self.preview.send('speak',text='Radio voice preview. Your next adventure awaits, Commander.',
                voice='' if self.voice.get()=='Windows Default' else self.voice.get(),rate=self.vars['voice_rate'].get(),
                pitch=self.vars['voice_pitch'].get(),volume=self.vars['voice_volume'].get())
            if not ok:self.preview_busy=False
            self.voice_status.configure(text='Voice Preview');self._poll_preview()

    def stop_preview(self):
        if self.preview is not None:self.preview.close();self.preview=None
        self.preview_busy=False
        self.voice_status.configure(text='Preview Stopped')

    def reset_voice(self):
        self.voice.set('Windows Default')
        for key in ('voice_rate','voice_pitch','voice_volume'):self.vars[key].set(self.api.DEFAULT_SETTINGS[key])

    def _poll_preview(self):
        if self.preview_job is not None or not self.alive():return
        self.preview_job=self.frame.after(100,self._drain_preview)

    def _drain_preview(self):
        self.preview_job=None
        if not self.alive() or self.preview is None:return
        for event in self.preview.drain():
            if event.get('ev')=='voices':
                if self.preview_task=='voices':self.preview_busy=False
                names=event.get('names') or []
                if isinstance(names,str):names=[names]
                self.voices=['Windows Default']+list(names)
                self.voice_box.configure(values=self.voices)
                self.voice_status.configure(text='Installed Voices Loaded. Pitch Response Varies By Voice.')
            elif event.get('ev') in ('error','notice'):
                self.voice_status.configure(text=event.get('msg') or 'Voice Preview Unavailable')
                if event.get('ev')=='error':self.preview_busy=False
            elif event.get('ev')=='state' and event.get('state')=='ended':
                self.preview_busy=False
                self.voice_status.configure(text='Preview Finished')
        # Poll only this helper's pending command/audio lifecycle, never the theme.
        if self.preview_busy and self.preview.running():self._poll_preview()
        elif self.preview is not None:self.preview.close();self.preview=None

    def apply(self):
        api=self.api
        previous=api._current_station();previous_id=previous['id'] if previous else None
        old_source=api._settings['source']
        api._remember_music()
        api._library=copy.deepcopy(self.library)
        api._library['streams']=api.stream_groups.normalize(api._library['streams'])
        for key,var in self.vars.items():api._settings[key]=var.get()
        api._settings['voice']='' if self.voice.get()=='Windows Default' else self.voice.get()
        stations=api._stations(old_source)
        if previous_id and not any(i['id']==previous_id for i in stations):
            api._stop()
            if stations:api._settings['station'][old_source]=stations[0]['id']
            elif old_source not in api._available_sources():api._settings['source']='dw3'
            api._load_tracks()
        elif old_source=='music' and not api._tracks and api._state=='stopped':api._load_tracks()
        elif old_source=='galnet' and api._state=='stopped':api._load_tracks()
        api._save_library();api._save_settings()
        if api._engine.running():
            api._engine.send('volume',value=api._settings['volume'],voice_value=api._settings['voice_volume'])
        api._refresh()

    def _destroy(self,event):
        if event.widget is self.frame:self.close()

    def close(self):
        if self.closed:return
        self.closed=True
        if self.preview_job is not None:
            try:self.frame.after_cancel(self.preview_job)
            except tk.TclError:pass
            self.preview_job=None
        if self.preview is not None:self.preview.close();self.preview=None
