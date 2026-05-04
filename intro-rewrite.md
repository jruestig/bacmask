Handoff: Collapse the dual keyboard / action-dispatch path                                              
                                                                                                          
  Goal                                                                           
                                                                                                          
  There is currently one action vocabulary (Action(name=…) from bacmask/ui/input/events.py) but two       
  separate dispatchers that translate it into service calls. They have overlapping but non-identical
  behavior. Consolidate into one dispatcher.                                                              
                                                                                 
  This is item 2 of three pre-Android cleanups. Item 1 (I/O source carriers) is already done — see        
  knowledge/035-io-source-carriers.md. Don't touch I/O.
                                                                                                          
  Current state — verified                                                       
                                                      
  Path A: window-level keyboard (bacmask/ui/app.py)                                                       
  - Window.bind(on_key_down=self._on_key_down) at app.py:41
  - _on_key_down (app.py:57-78) translates Kivy key codes via local _kivy_key_name map (app.py:378-397),  
  calls keybinding_for(key, modifiers) from bacmask.ui.input.desktop_adapter to get an action name, then
  calls _run_action.                                                                                      
  - _run_action (app.py:80-131) is the dispatcher: close_lasso, cancel_stroke, undo, redo, delete_region,
  save_bundle, export_csv, select_lasso/brush/line, toggle_brush_mode, load_image, pan_left/right/up/down.
  - Has guards: _open_modal_count (skip when popup is open), _text_input_focused (skip when a TextInput   
  owns focus).                                                                                         
                                                                                                          
  Path B: canvas-emitted Actions (bacmask/ui/widgets/image_canvas.py)            
  - DesktopInputAdapter(emit=self._on_input) at image_canvas.py:128.                                      
  - _on_input (image_canvas.py:697-740) handles pointer/zoom/pan events, and dispatches Action events to  
  _handle_action.                                                                                         
  - _handle_action (image_canvas.py:877-…) is a second dispatcher that overlaps with _run_action for      
  close_lasso, cancel_stroke, undo, redo, delete_region, select_lasso/brush/line. It additionally clears
  _brush_preview_pts on cancel_stroke — a canvas-internal that the app-side dispatcher does not know      
  about.                                                                                            
                                                                                                          
  The dead bit: DesktopInputAdapter.on_key_down (bacmask/ui/input/desktop_adapter.py:167-173) exists but
  is never called. Kivy delivers key events to Window, not to widgets. The adapter's keyboard translation 
  method is unreachable code.
                                                                                                          
  Why this is a problem                                                                                   
                                                      
  1. Two sources of truth for action behavior. When cancel_stroke is pressed while a brush stroke is in   
  progress, Path A doesn't clear _brush_preview_pts — visible artifact, narrowly avoided today only
  because Path A is the only one that fires for keyboard.                                                 
  2. The input-abstraction layer doesn't earn its keep. Knowledge note 016 sells "widgets and services
  consume semantic events — they never see raw Kivy events." App.py does see raw Kivy events. When the    
  touch adapter is swapped in for Android, Window.on_key_down becomes dead on tablets, but _run_action is
  the only place that knows what save_bundle / load_image / pan_* do — those can't live in the canvas     
  dispatcher because they need file dialogs and screen access.                   
  3. Adding a new action requires editing two dispatchers and remembering both. Easy to miss.
                                                                                                          
  Proposed design                                                                                         
                                                                                                          
  Single dispatcher in app.py. Canvas becomes a pure translator: it emits Action events upward, app       
  handles them. DesktopInputAdapter becomes the only key/touch translator.       
                                                                                                          
  Concrete shape:                                                                
                                                      
  1. BacMaskApp exposes one public dispatch_action(name: str) -> bool — what _run_action does today, but  
  renamed and addressable from the canvas. Returns True if the action was handled. Move _run_action's body
   verbatim; this is a rename, not a logic change.                                                        
  2. ImageCanvas accepts an on_action: Callable[[str], bool] callback in its constructor. Replace
  _handle_action body with self._on_action(event.name). Drop the per-action branching in the canvas — the 
  app-side dispatcher handles all of them.
  3. MainScreen plumbs the callback from BacMaskApp.dispatch_action to ImageCanvas. Update                
  MainScreen.__init__ signature in bacmask/ui/screens/main_screen.py.                                     
  4. Move canvas-internal cleanup out of the dispatcher. The _brush_preview_pts = [] in current
  _handle_action at cancel_stroke is the only canvas-specific side-effect. Make the canvas subscribe to   
  MaskService state changes (it already does, see image_canvas.py — it has a _last_regions_version cache)
  and clear _brush_preview_pts when state.active_brush_stroke transitions from non-None to None. That way 
  the cleanup is an effect of the state change, not an effect of which key was pressed.
  5. Window-level keyboard handler in app.py keeps its guards (_open_modal_count, _text_input_focused).
  Continue to call keybinding_for for translation, then dispatch_action. Do not try to route window keys  
  through DesktopInputAdapter.on_key_down — that adapter instance lives inside the canvas widget; the
  window key path doesn't have access to it. Two viable resolutions for the dead on_key_down method on the
   adapter:                                                                      
    - (a) Delete it. App.py is the only window-key consumer; the adapter is for pointer events.
    - (b) Keep it but make app.py instantiate its own DesktopInputAdapter(emit=lambda e: ...) purely for  
  keyboard, sharing the translation logic with the canvas. More uniform, slightly more wiring.            
                                                                                                          
  I'd default to (a) — simpler, and the translation already lives in the standalone keybinding_for        
  function which both can call.                                                  
                                                                                                          
  Files that change                                                              
                                                      
  4. Move canvas-internal cleanup out of the dispatcher. The _brush_preview_pts = [] in current _handle_action at cancel_stroke is the only canvas-specific side-effect. Make the canvas subscribe to MaskService
  state changes (it already does, see image_canvas.py — it has a _last_regions_version cache) and clear _brush_preview_pts when state.active_brush_stroke transitions from non-None to None. That way the cleanup is
  an effect of the state change, not an effect of which key was pressed.
  5. Window-level keyboard handler in app.py keeps its guards (_open_modal_count, _text_input_focused). Continue to call keybinding_for for translation, then dispatch_action. Do not try to route window keys
  through DesktopInputAdapter.on_key_down — that adapter instance lives inside the canvas widget; the window key path doesn't have access to it. Two viable resolutions for the dead on_key_down method on the
  adapter:
    - (a) Delete it. App.py is the only window-key consumer; the adapter is for pointer events.
    - (b) Keep it but make app.py instantiate its own DesktopInputAdapter(emit=lambda e: ...) purely for keyboard, sharing the translation logic with the canvas. More uniform, slightly more wiring.

  I'd default to (a) — simpler, and the translation already lives in the standalone keybinding_for function which both can call.

  Files that change

  - bacmask/ui/app.py — rename _run_action → dispatch_action, expose as instance method; pass to MainScreen.
  - bacmask/ui/screens/main_screen.py — new on_action parameter, forwarded to ImageCanvas.
  - bacmask/ui/widgets/image_canvas.py — new constructor param on_action; replace _handle_action with single forward call; move _brush_preview_pts reset into a state-subscription side effect.
  - bacmask/ui/input/desktop_adapter.py — delete DesktopInputAdapter.on_key_down if going with resolution (a). Keep keybinding_for and the rest.

  Files that should NOT change

  - bacmask/core/* — no UI imports, not touched.
  - bacmask/services/mask_service.py — already the action target, no change.
  - bacmask/ui/input/events.py — vocabulary stays.
  - The keybinding registry in desktop_adapter.py — leave alone.

  Tests

  - Existing keyboard tests in tests/ui/test_input_events.py are pure registry tests on keybinding_for / label_for_action / button_label. They should keep passing without modification.
  - Canvas tests in tests/ui/test_image_canvas_*.py may need light updates — check whether any test triggers _handle_action directly. If yes, replace with calls through the new on_action callback or directly
  through BacMaskApp.dispatch_action.
  - Add one new test: cancel_stroke from window keyboard while a brush stroke is in flight clears the canvas preview points. This is the bug the dual dispatch was hiding.

  Acceptance

  - uv run --extra dev pytest — all green (currently 225 tests after item 1).
  - uv run --extra dev ruff check bacmask tests — clean.
  - uv run --extra dev ruff format --check bacmask tests — clean.
  - Manual smoke: launch with uv run python main.py images/<some>.tif, draw a lasso, press Esc mid-stroke (preview disappears), press B then start a brush stroke, press Esc mid-stroke (preview disappears, no
  leftover dots), Ctrl+Z undoes, Ctrl+S opens Save As.

  Knowledge base

  When done, update knowledge/016-input-abstraction.md (note that window-level keys go through keybinding_for directly, not through the adapter — or however resolution lands), and add a new note
  knowledge/036-single-action-dispatcher.md in the same caveman style as 035. Mark frontmatter created: <today> and add bidirectional related links.
