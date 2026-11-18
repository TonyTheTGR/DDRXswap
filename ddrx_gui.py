#!/usr/bin/env python3
"""DDR X USA Song Swap desktop interface (Tkinter, bundled with Python)."""
import json
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import ddrx_converter as converter


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('DDR X USA Song Swap — Experimental')
        self.geometry('970x670')
        self.minsize(760, 560)
        self.iso = tk.StringVar()
        self.output = tk.StringVar()
        self.song = tk.StringVar()
        self.banner = tk.BooleanVar(value=True)
        self.charts_only = tk.BooleanVar(value=False)
        self.update_ratings = tk.BooleanVar(value=True)
        self.update_bpm = tk.BooleanVar(value=True)
        self.shock_mode = tk.StringVar(value="ignore")
        self.jobs = []
        self.slots = []
        self.slot = tk.StringVar()
        self.busy = False
        self.make_widgets()

    def make_widgets(self):
        top = ttk.Frame(self, padding=12)
        top.pack(fill='x')
        ttk.Label(top, text='DDR X USA — Song Replacement', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        ttk.Label(top, text='Creates a new ISO. Title cards and corrected X-scale ratings; chart availability requires in-game verification. BPM min/max updates supported; Shock Arrows are experimental.').pack(anchor='w', pady=(2, 12))
        for label, var, callback in (
                ('Original DDR X ISO', self.iso, self.select_iso),
                ('New output ISO', self.output, self.select_output),
                ('StepMania folder / ZIP / simfile', self.song, self.select_song)):
            line = ttk.Frame(top)
            line.pack(fill='x', pady=3)
            ttk.Label(line, text=label, width=29).pack(side='left')
            ttk.Entry(line, textvariable=var).pack(side='left', fill='x', expand=True, padx=5)
            ttk.Button(line, text='Browse…', command=callback).pack(side='right')
        mid = ttk.Frame(self, padding=(12, 5))
        mid.pack(fill='x')
        ttk.Button(mid, text='Scan stock song slots', command=self.scan_slots).pack(side='left')
        ttk.Label(mid, text='Replace original slot:').pack(side='left', padx=(15, 5))
        self.slotbox = ttk.Combobox(mid, textvariable=self.slot, state='readonly', width=46)
        self.slotbox.pack(side='left', fill='x', expand=True)
        ttk.Button(mid, text='Add to batch', command=self.add_job).pack(side='left', padx=8)
        flags = ttk.Frame(self, padding=(12, 4))
        flags.pack(fill='x')
        ttk.Checkbutton(flags, text='Replace banner (title card always generated)', variable=self.banner).pack(side='left')
        ttk.Checkbutton(flags, text='Charts only (no audio)', variable=self.charts_only).pack(side='left', padx=20)
        ttk.Checkbutton(flags, text='Update X-scale difficulty ratings (v0.3.1 fix)', variable=self.update_ratings).pack(side='left', padx=15)
        extras = ttk.Frame(self, padding=(12, 4))
        extras.pack(fill='x')
        ttk.Checkbutton(extras, text='Update song-select BPM min/max', variable=self.update_bpm).pack(side='left')
        ttk.Label(extras, text='Shock Arrows:').pack(side='left', padx=(22, 6))
        ttk.Combobox(extras, textvariable=self.shock_mode, state='readonly', width=18,
                     values=('ignore', 'all', 'any')).pack(side='left')
        ttk.Label(extras, text='ignore / all-panel / any mine (mixed: 1/16 earlier)').pack(side='left', padx=8)
        ttk.Label(self, text='Queued replacements — add as many different stock slots as desired', padding=(12, 7)).pack(anchor='w')
        self.table = ttk.Treeview(self, columns=('slot', 'source', 'banner'), show='headings', height=7)
        for col, heading, width in [('slot', 'Slot', 200), ('source', 'StepMania source', 540), ('banner', 'Banner', 80)]:
            self.table.heading(col, text=heading)
            self.table.column(col, width=width, stretch=(col == 'source'))
        self.table.pack(fill='both', expand=True, padx=12)
        actions = ttk.Frame(self, padding=12)
        actions.pack(fill='x')
        ttk.Button(actions, text='Remove selected', command=self.remove_job).pack(side='left')
        ttk.Button(actions, text='Save job list…', command=self.save_jobs).pack(side='left', padx=8)
        ttk.Button(actions, text='Load job list…', command=self.load_jobs).pack(side='left')
        self.go = ttk.Button(actions, text='Create modified ISO', command=self.build)
        self.go.pack(side='right')
        ttk.Label(self, text='Progress log:', padding=(12, 0)).pack(anchor='w')
        self.log = tk.Text(self, height=9, font=('Consolas', 9), wrap='word', state='disabled')
        self.log.pack(fill='both', expand=True, padx=12, pady=(4, 12))

    def select_iso(self):
        v = filedialog.askopenfilename(filetypes=[('ISO image', '*.iso'), ('All files', '*.*')])
        if v:
            self.iso.set(v)
            self.slots = []
            self.slotbox['values'] = []

    def select_output(self):
        v = filedialog.asksaveasfilename(defaultextension='.iso', filetypes=[('ISO image', '*.iso')])
        if v:
            self.output.set(v)

    def select_song(self):
        v = filedialog.askopenfilename(title='Choose song ZIP, .sm or .ssc',
                                       filetypes=[('Songs', '*.zip *.sm *.ssc'), ('All files', '*.*')])
        if not v:
            v = filedialog.askdirectory(title='Or choose a StepMania song folder')
        if v:
            self.song.set(v)

    def notify(self, text):
        self.after(0, lambda: self._log(text))

    def _log(self, text):
        self.log.configure(state='normal')
        self.log.insert('end', str(text) + '\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def scan_slots(self):
        try:
            g = converter.DDRXGame(Path(self.iso.get()))
            self.slots = [(code, rec['index'], g.title_map.get(code, code))
                          for code, rec in sorted(g.slot_map.items(), key=lambda v: v[1]['index'])]
            self.slotbox['values'] = [f'{index:02d} | {code:<5} | {title}'
                                      for code, index, title in self.slots]
            if self.slots:
                self.slotbox.current(0)
            self._log(f'Found {len(self.slots)} verified stock DDR X song slots.')
        except Exception as e:
            messagebox.showerror('Cannot scan ISO', str(e))

    def add_job(self):
        if not self.slots:
            messagebox.showwarning('Scan first', 'Choose an ISO and scan its song slots first.')
            return
        idx = self.slotbox.current()
        if idx < 0:
            return
        code = self.slots[idx][0]
        source = Path(self.song.get())
        if not source.exists():
            messagebox.showwarning('No song', 'Select an existing StepMania ZIP, folder or simfile.')
            return
        if any(j['slot'] == code for j in self.jobs):
            messagebox.showwarning('Duplicate slot', f'{code} is already in this batch.')
            return
        self.jobs.append({'slot': code, 'song': str(source.resolve()), 'banner': self.banner.get()})
        self.redraw()

    def redraw(self):
        for row in self.table.get_children():
            self.table.delete(row)
        for i, job in enumerate(self.jobs):
            self.table.insert('', 'end', iid=str(i), values=(job['slot'], job['song'], 'yes' if job['banner'] else 'no'))

    def remove_job(self):
        chosen = sorted([int(x) for x in self.table.selection()], reverse=True)
        for idx in chosen:
            self.jobs.pop(idx)
        self.redraw()

    def save_jobs(self):
        if not self.jobs:
            return
        name = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON', '*.json')])
        if name:
            Path(name).write_text(json.dumps(self.jobs, indent=2), encoding='utf-8')

    def load_jobs(self):
        name = filedialog.askopenfilename(filetypes=[('JSON', '*.json')])
        if name:
            try:
                content = json.loads(Path(name).read_text(encoding='utf-8'))
                if not isinstance(content, list):
                    raise ValueError('Expected a JSON list of jobs')
                self.jobs = content
                self.redraw()
            except Exception as e:
                messagebox.showerror('Invalid jobs', str(e))

    def build(self):
        if self.busy:
            return
        if not self.jobs or not self.iso.get() or not self.output.get():
            messagebox.showwarning('Missing input', 'Select ISO, output path, and add at least one replacement.')
            return
        if not messagebox.askyesno('Experimental ISO modification',
                'This build is NOT boot-tested. Original background videos, unlocks, '
                'Chart-availability flags and unlocks remain stock. Shock Arrow encoding is experimental.\n\n'
                'Create a separate ISO and test it in PCSX2?'):
            return
        self.busy = True
        self.go.configure(state='disabled')
        jobs = [dict(j) for j in self.jobs]
        iso, out, charts_only = Path(self.iso.get()), Path(self.output.get()), self.charts_only.get()
        update_ratings = self.update_ratings.get()
        update_bpm = self.update_bpm.get()
        shock_mode = self.shock_mode.get()

        def worker():
            try:
                # Console progress is captured in normal CLI; GUI shows final status.
                warnings = converter.make_iso(iso, out, jobs, charts_only=charts_only, update_ratings=update_ratings,
                                              update_bpm=update_bpm, shock_mode=shock_mode)
                self.notify('SUCCESS: ' + str(out))
                for warning in warnings:
                    self.notify(warning)
                success_msg = 'Created: ' + str(out) + '\nTest it in PCSX2 first.'
                if warnings:
                    success_msg += '\n\nArtwork warnings:\n' + '\n'.join(warnings)
                self.after(0, lambda: messagebox.showinfo('ISO generated', success_msg))
            except Exception:
                err = traceback.format_exc()
                self.notify('FAILED:\n' + err)
                self.after(0, lambda: messagebox.showerror('Conversion failed', err[-1400:]))
            finally:
                self.after(0, self.finish)
        threading.Thread(target=worker, daemon=True).start()

    def finish(self):
        self.busy = False
        self.go.configure(state='normal')


if __name__ == '__main__':
    App().mainloop()
