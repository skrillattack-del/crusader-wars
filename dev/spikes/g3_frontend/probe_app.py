"""Double-click operator for the G1 experiment. No CK3 writes."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
import probe

def main():
    app = tk.Tk()
    app.title('Crusader Wars → Three Kingdoms | G1 experiment')
    app.geometry('850x650')
    base = Path(sys.executable).parent if getattr(sys, 'frozen', False) else probe.HERE
    cli_default = next((p / 'tools/rpfm/rpfm_cli.exe' for p in (base, *base.parents)
                        if (p / 'tools/rpfm/rpfm_cli.exe').is_file()), Path('rpfm_cli.exe'))
    game = tk.StringVar(value=str(probe.GAME))
    cli = tk.StringVar(value=str(cli_default))
    state_file = base / 'cw2-probe-session.json'
    session = {'output': None}
    if state_file.exists():
        try: session.update(json.loads(state_file.read_text(encoding='utf-8')))
        except (ValueError, OSError): pass
    frame = ttk.Frame(app, padding=18)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Three Kingdoms battle bridge — G1', font=('Segoe UI', 17, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='Experimental battle staging and result capture. Full CK3 round-trip is not implemented.', wraplength=790).pack(anchor='w', pady=(5, 15))
    for title, variable, directory in [('Three Kingdoms install folder', game, True), ('RPFM CLI', cli, False)]:
        ttk.Label(frame, text=title).pack(anchor='w')
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=(0, 10))
        ttk.Entry(row, textvariable=variable).pack(side='left', fill='x', expand=True)
        def browse(v=variable, d=directory):
            path = filedialog.askdirectory() if d else filedialog.askopenfilename(filetypes=[('Executable', '*.exe')])
            if path: v.set(path)
        ttk.Button(row, text='Browse', command=browse).pack(side='right')
    instructions = ('1. Close Three Kingdoms, then Prepare and install.\n'
                    '2. Open 3K and enable cw2_g1_probe in its mod manager.\n'
                    '3. Select Historical Battles → Xingyang (internal: xinyang), Records mode.\n'
                    '4. Confirm Cao Cao versus Liu Bei, each with Ji Militia and Archer Militia.\n'
                    '5. Fight to the results screen, then Read result. Do not replay this run.\n'
                    '6. Close 3K and Remove probe to restore the original historical battle.\n\n'
                    'If the menu, roster or log differs, stop and retain the run folder for diagnosis.')
    ttk.Label(frame, text=instructions, justify='left', wraplength=790).pack(anchor='w', pady=10)
    buttons = ttk.Frame(frame)
    buttons.pack(fill='x', pady=10)
    log = tk.Text(frame, height=12, wrap='word')
    log.pack(fill='both', expand=True)
    messages = queue.Queue()
    busy = False
    def say(text):
        log.insert('end', text + '\n')
        log.see('end')
    def current():
        if not session.get('output'): raise ValueError('Prepare a run first.')
        return Path(session['output'])
    def closed():
        result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Three_Kingdoms.exe', '/FO', 'CSV', '/NH'],
                                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode or 'Three_Kingdoms.exe' in result.stdout:
            raise ValueError('Close Three Kingdoms before changing the experiment pack.')
    def prepare(game_path, cli_path):
        closed()
        if (Path(game_path) / 'data' / probe.PACK_NAME).exists():
            raise ValueError('Remove the installed probe before preparing a fresh run.')
        output = base / 'runs' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        probe.build(game_path, cli_path, output)
        session.update(output=str(output), game=game_path)
        state_file.write_text(json.dumps(session, indent=2), encoding='utf-8')
        probe.install(game_path, output)
        return f'Prepared and installed: {output}\nNow enable the mod and run the Records historical battle.'
    def remove():
        closed()
        probe.uninstall(session['game'], current())
        return 'Probe removed. Original CA packs were never modified.'
    def work(fn):
        nonlocal busy
        if busy: return
        busy = True
        for button in buttons.winfo_children(): button.config(state='disabled')
        say('Working…')
        def worker():
            try: messages.put((True, str(fn())))
            except Exception as exc: messages.put((False, str(exc)))
        threading.Thread(target=worker, daemon=True).start()
    def poll():
        nonlocal busy
        try:
            success, text = messages.get_nowait()
            say(('OK: ' if success else 'Needs attention: ') + text)
            busy = False
            for button in buttons.winfo_children(): button.config(state='normal')
        except queue.Empty: pass
        app.after(100, poll)
    def start_prepare():
        gp, cp = game.get(), cli.get()
        work(lambda: prepare(gp, cp))
    ttk.Button(buttons, text='Prepare and install', command=start_prepare).pack(side='left', padx=3)
    ttk.Button(buttons, text='Open Three Kingdoms', command=lambda: os.startfile('steam://rungameid/779340')).pack(side='left', padx=3)
    ttk.Button(buttons, text='Read result', command=lambda: work(lambda: json.dumps(probe.read_result(current()), indent=2))).pack(side='left', padx=3)
    ttk.Button(buttons, text='Remove probe', command=lambda: work(remove)).pack(side='left', padx=3)
    def folder():
        try: os.startfile(str(current()))
        except Exception as exc: messagebox.showerror('Run folder', str(exc))
    ttk.Button(buttons, text='Run folder', command=folder).pack(side='left', padx=3)
    def close():
        if busy: messagebox.showinfo('Working', 'Wait for the current operation to finish before closing.')
        else: app.destroy()
    app.protocol('WM_DELETE_WINDOW', close)
    say('G1 remains open until a real battle verifies the staged roster and result.')
    if session.get('output'): say('Previous run: ' + session['output'])
    app.after(100, poll)
    if '--smoke-test' in sys.argv:
        app.withdraw()
        if not (probe.HERE / 'probe.lua').is_file():
            raise RuntimeError('Packaged Lua resource is missing.')
        app.after(300, app.destroy)
    app.mainloop()

if __name__ == '__main__': main()
