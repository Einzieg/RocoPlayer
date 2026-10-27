; The frozen helper writes persistent logs and queries SCM/PnP without loading DD.
!macro NSIS_HOOK_POSTINSTALL
  IfFileExists "$INSTDIR\drivers\dd\drv\ddc.exe" 0 roco_dd_done
  SetShellVarContext all
  CreateDirectory "$APPDATA\RocoPlayer\logs"
  ClearErrors
  FileOpen $1 "$APPDATA\RocoPlayer\logs\dd-bootstrap.log" a
  IfErrors roco_dd_log_failed
  FileWrite $1 "DD setup requested: $INSTDIR$\r$\n"
  FileClose $1
  SetOutPath "$INSTDIR"
  nsExec::ExecToLog /TIMEOUT=180000 '"$INSTDIR\engine\rock-music-engine.exe" --dd-setup --driver-dir "$INSTDIR\drivers\dd\drv" --log-dir "$APPDATA\RocoPlayer\logs"'
  Pop $0
  FileOpen $1 "$APPDATA\RocoPlayer\logs\dd-bootstrap.log" a
  FileWrite $1 "DD helper exit: $0$\r$\n"
  FileClose $1
  StrCmp $0 "0" roco_dd_ready
  StrCmp $0 "3010" roco_dd_reboot
  StrCmp $0 "timeout" roco_dd_reboot
  MessageBox MB_OK|MB_ICONEXCLAMATION "DD setup or device checks failed. Application files are installed, but DD is not confirmed ready. Do not repeatedly reinstall the driver. Diagnostic logs: $APPDATA\RocoPlayer\logs"
  Goto roco_dd_done
roco_dd_ready:
  DetailPrint "DD service and present PnP devices are ready. No keyboard input was tested."
  Goto roco_dd_done
roco_dd_reboot:
  SetRebootFlag true
  MessageBox MB_OK|MB_ICONEXCLAMATION "DD setup requires a restart or timed out. Save your work and restart Windows. Do not rerun DD installation immediately. Review logs in $APPDATA\RocoPlayer\logs if DD remains unavailable."
  Goto roco_dd_done
roco_dd_log_failed:
  MessageBox MB_OK|MB_ICONEXCLAMATION "Cannot create DD installation logs. DD setup was skipped. Check permissions for $APPDATA\RocoPlayer\logs."
roco_dd_done:
  SetOutPath "$INSTDIR"
!macroend

; Never uninstall the shared system driver automatically with the application.
