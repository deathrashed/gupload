tell application "System Events" to set frontApp to name of first process whose frontmost is true

tell application "System Events"
	tell application process frontApp
		set _selection to value of attribute "AXFocusedUIElement"
		tell _selection to perform action "AXShowMenu"
	end tell
end tell