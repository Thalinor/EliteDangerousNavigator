# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Jonathan Estok ("Commander Thalinor"). See LICENSE and CREDITS.txt.
"""Remember ordinary Tk popups through map/configure/destroy events."""
import ctypes
import json
import re
import tkinter as tk
from ctypes import wintypes

KEY = 'NavInterface_PopupGeometry'


def screens(root):
    """Work areas retain negative coordinates on monitors left of the primary."""
    result = []
    try:
        user = ctypes.WinDLL('user32', use_last_error=True)
        class Info(ctypes.Structure):
            _fields_ = [('size',wintypes.DWORD),('monitor',wintypes.RECT),('work',wintypes.RECT),('flags',wintypes.DWORD)]
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HANDLE,wintypes.HDC,ctypes.POINTER(wintypes.RECT),wintypes.LPARAM)
        user.GetMonitorInfoW.argtypes = [wintypes.HANDLE,ctypes.POINTER(Info)]
        def collect(handle, _dc, _rect, _data):
            info = Info(); info.size = ctypes.sizeof(info)
            if user.GetMonitorInfoW(handle,ctypes.byref(info)):
                r=info.work; result.append((r.left,r.top,r.right,r.bottom))
            return True
        callback = callback_type(collect)
        user.EnumDisplayMonitors(None,None,callback,0)
    except (AttributeError,OSError):
        pass
    return result or [(0,0,root.winfo_screenwidth(),root.winfo_screenheight())]


def visible_geometry(value, areas):
    width,height,x,y = (int(n) for n in value)
    area = max(areas,key=lambda r:max(0,min(x+width,r[2])-max(x,r[0]))*max(0,min(y+height,r[3])-max(y,r[1])))
    left,top,right,bottom=area
    width=max(160,min(width,right-left)); height=max(100,min(height,bottom-top-35))
    x=max(left,min(x,right-width)); y=max(top+30,min(y,bottom-height))
    return width,height,x,y


def geometry_text(value):
    width,height,x,y=value
    # + followed by a signed number denotes an absolute virtual-screen
    # coordinate; bare - means distance from the right/bottom in Tk.
    return '{}x{}+{}+{}'.format(width,height,x,y)


class WindowMemory:
    def __init__(self,root,config):
        self.root,self.config=root,config
        self.records={}; self.saved={}; self.pending=None; self.jobs={}; self.closed=False
        try:
            data=json.loads(config.get_str(KEY,default='{}') or '{}')
            if isinstance(data,dict):
                for key,value in data.items():
                    if isinstance(key,str) and isinstance(value,list) and len(value)==4 and all(isinstance(n,int) and not isinstance(n,bool) and abs(n)<100000 for n in value) and value[0]>0 and value[1]>0:
                        self.saved[key]=value
        except (ValueError,TypeError):
            pass
        self.bindings=[]
        for event,handler in (('<Map>',self.mapped),('<Configure>',self.configured),('<Destroy>',self.destroyed)):
            self.bindings.append((event,root.bind_all(event,handler,add='+')))

    def identity(self,window):
        explicit=getattr(window,'navigator_window_id',None)
        if explicit:return str(explicit)
        cls=type(window)
        if cls is not tk.Toplevel:
            return cls.__module__+':'+cls.__qualname__
        owner=window.master
        while owner is not None and type(owner).__module__ in ('tkinter','tkinter.ttk'):
            owner=getattr(owner,'master',None)
        owner_type=type(owner) if owner is not None else type(self.root)
        return owner_type.__module__+':'+owner_type.__qualname__+':'+window.title()

    def attach(self,window):
        if self.closed or window is self.root or window in self.records:return
        if not getattr(window,'navigator_window_memory',True):return
        try:
            if not isinstance(window,tk.Toplevel) or window.overrideredirect():return
            self.records[window]={'key':self.identity(window),'default':None,'last':None,'ready':False}
            if window.winfo_ismapped():
                self.jobs[window]=self.root.after_idle(lambda:self.restore(window))
        except tk.TclError:pass

    def mapped(self,event):
        if isinstance(event.widget,tk.Toplevel):
            window=event.widget
            self.attach(window)
            record=self.records.get(window)
            if record and not record['ready'] and window not in self.jobs:
                self.jobs[window]=self.root.after_idle(lambda:self.restore(window))

    def current(self,window):
        if window.state()!='normal':return None
        return [window.winfo_width(),window.winfo_height(),window.winfo_x(),window.winfo_y()]

    def restore(self,window):
        self.jobs.pop(window,None)
        record=self.records.get(window)
        if self.closed or record is None:return
        try:
            current=self.current(window)
            if current:
                # Read requested size after the shared styling pass. Fixed
                # pixel defaults can be too small for the actual font/DPI.
                natural=[max(current[0],window.winfo_reqwidth()),
                         max(current[1],window.winfo_reqheight()),current[2],current[3]]
                record['default']=list(visible_geometry(natural,screens(self.root)))
            wanted=self.saved.get(record['key'],record['default'])
            if wanted:
                wanted=visible_geometry(wanted,screens(self.root))
                window.geometry(geometry_text(wanted))
                window.lift()
            record['ready']=True
            record['last']=list(wanted) if wanted else None
        except tk.TclError:pass

    def configured(self,event):
        record=self.records.get(event.widget)
        if not record or not record['ready'] or self.closed:return
        try:
            value=self.current(event.widget)
            if value and value[0]>1 and value[1]>1:
                record['last']=value
                self.saved[record['key']]=value
                self.schedule_save()
        except tk.TclError:pass

    def schedule_save(self):
        if self.pending is not None:
            self.root.after_cancel(self.pending)
        # A one-shot debounce after geometry changes, not a polling loop.
        self.pending=self.root.after(250,self.flush)

    def flush(self):
        if self.pending is not None:
            try:self.root.after_cancel(self.pending)
            except tk.TclError:pass
        self.pending=None
        self.config.set(KEY,json.dumps(self.saved,sort_keys=True))

    def destroyed(self,event):
        window=event.widget
        record=self.records.pop(window,None)
        if record and record['last']:
            self.saved[record['key']]=record['last']; self.schedule_save()
        job=self.jobs.pop(window,None)
        if job:
            try:self.root.after_cancel(job)
            except tk.TclError:pass

    def reset(self):
        self.saved.clear()
        for window,record in list(self.records.items()):
            try:
                if record['default']:
                    value=visible_geometry(record['default'],screens(self.root))
                    window.geometry(geometry_text(value)); window.lift()
                    record['last']=list(value)
            except tk.TclError:pass
        self.flush()

    def close(self):
        self.closed=True
        self.flush()
        for job in self.jobs.values():
            try:self.root.after_cancel(job)
            except tk.TclError:pass
        for event,binding in self.bindings:
            script=str(self.root.tk.call('bind','all',event))
            self.root.tk.call('bind','all',event,'\n'.join(line for line in script.splitlines() if binding not in line))
            try:self.root.deletecommand(binding)
            except tk.TclError:pass
        self.jobs.clear(); self.records.clear()
