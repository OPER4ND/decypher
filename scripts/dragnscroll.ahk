#Requires AutoHotkey v2.0

global DragScrollEnabled := true
global DragScrollActive := false
global DragScrollEngaged := false
global AnchorX := 0
global AnchorY := 0
global ScrollAccumulator := 0

; Tuning
global PixelsPerNotch := 25
global PollIntervalMs := 10
global DragStartThresholdPx := 8

; Toggle drag-scroll on/off
^!Backspace::
{
    global DragScrollEnabled, DragScrollActive

    DragScrollEnabled := !DragScrollEnabled

    if !DragScrollEnabled && DragScrollActive
    {
        SetTimer DragScrollTick, 0
        DragScrollActive := false
    }

    TrayTip "Drag Scroll", DragScrollEnabled ? "Enabled" : "Disabled", 1000
}

*RButton::
{
    global DragScrollEnabled, DragScrollActive, DragScrollEngaged, AnchorX, AnchorY, ScrollAccumulator, PollIntervalMs

    if !DragScrollEnabled
    {
        Send "{RButton down}"
        KeyWait "RButton"
        Send "{RButton up}"
        return
    }

    DragScrollActive := true
    DragScrollEngaged := false
    ScrollAccumulator := 0

    MouseGetPos &AnchorX, &AnchorY
    SetTimer DragScrollTick, PollIntervalMs

    KeyWait "RButton"

    SetTimer DragScrollTick, 0
    DragScrollActive := false
    if DragScrollEngaged
        DllCall("SetCursorPos", "int", AnchorX, "int", AnchorY)
    else
        Click "Right"
}

DragScrollTick()
{
    global DragScrollActive, DragScrollEngaged, AnchorX, AnchorY, ScrollAccumulator, PixelsPerNotch, DragStartThresholdPx

    if !DragScrollActive
        return

    MouseGetPos &mx, &my
    dy := my - AnchorY

    if !DragScrollEngaged
    {
        dx := mx - AnchorX
        if Abs(dx) < DragStartThresholdPx && Abs(dy) < DragStartThresholdPx
            return
        DragScrollEngaged := true
    }

    ScrollAccumulator += dy

    DllCall("SetCursorPos", "int", AnchorX, "int", AnchorY)

    ; move mouse down -> page goes up
    ; move mouse up   -> page goes down
    while ScrollAccumulator >= PixelsPerNotch
    {
        Send "{WheelUp}"
        ScrollAccumulator -= PixelsPerNotch
    }

    while ScrollAccumulator <= -PixelsPerNotch
    {
        Send "{WheelDown}"
        ScrollAccumulator += PixelsPerNotch
    }
}
