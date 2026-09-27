# Paints the static art of the in-game CRUSADER WARS II lobby (ui/cw2/*.png).
# Dynamic text (names, numbers, units) is drawn by the game on top; positions
# match lobby.py's LAYOUT. Sources: the launcher's CK3 skin crops and fonts in
# dev/app/ui/skins/ck3. Run: powershell -ExecutionPolicy Bypass -File make_art.ps1
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$here = $PSScriptRoot
$skin = Join-Path $here '..\..\..\app\ui\skins\ck3'
$out = Join-Path $here 'ui\cw2'
New-Item -ItemType Directory -Force $out | Out-Null

$fonts = New-Object System.Drawing.Text.PrivateFontCollection
foreach ($f in 'cinzel.ttf', 'crimson-regular.ttf', 'crimson-semibold.ttf', 'crimson-bold.ttf') { $fonts.AddFontFile((Join-Path $skin $f)) }
function Family($name) { $fonts.Families | Where-Object { $_.Name -eq $name } | Select-Object -First 1 }
$cinzel = Family 'Cinzel'; $crimson = Family 'Crimson Text'
function Img($name) { [System.Drawing.Image]::FromFile((Join-Path $skin $name)) }
function Col($hex, $a = 255) { [System.Drawing.Color]::FromArgb($a, [Convert]::ToInt32($hex.Substring(1, 2), 16), [Convert]::ToInt32($hex.Substring(3, 2), 16), [Convert]::ToInt32($hex.Substring(5, 2), 16)) }
function Brush($hex, $a = 255) { New-Object System.Drawing.SolidBrush (Col $hex $a) }
function Pen($hex, $w = 1, $a = 255) { New-Object System.Drawing.Pen (Col $hex $a), $w }
function Rect($x, $y, $w, $h) { New-Object System.Drawing.RectangleF $x, $y, $w, $h }
function Canvas($w, $h) {
  $bmp = New-Object System.Drawing.Bitmap $w, $h, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.SmoothingMode = 'AntiAlias'; $g.InterpolationMode = 'HighQualityBicubic'; $g.TextRenderingHint = 'AntiAliasGridFit'
  return $bmp, $g
}
function Text($g, $s, $family, $size, $style, $hex, $x, $y, $w, $h, $align = 'Near', $alpha = 255) {
  $font = New-Object System.Drawing.Font $family, $size, ([System.Drawing.FontStyle]$style), ([System.Drawing.GraphicsUnit]::Pixel)
  $fmt = New-Object System.Drawing.StringFormat; $fmt.Alignment = $align; $fmt.LineAlignment = 'Center'
  $g.DrawString($s, $font, (Brush $hex $alpha), (Rect $x $y $w $h), $fmt)
}
# A torn brush stroke: a rectangle whose edges wander, seeded so reruns match.
function BrushPath($x, $y, $w, $h, $seed) {
  $rnd = New-Object System.Random $seed
  $pts = New-Object System.Collections.Generic.List[System.Drawing.PointF]
  $steps = 14
  for ($i = 0; $i -le $steps; $i++) { $pts.Add((New-Object System.Drawing.PointF ($x + $w * $i / $steps), ($y + $rnd.Next(0, [int]($h * .18))))) }
  for ($i = 0; $i -le 5; $i++) { $pts.Add((New-Object System.Drawing.PointF ($x + $w - $rnd.Next(0, [int]($w * .04))), ($y + $h * $i / 5))) }
  for ($i = $steps; $i -ge 0; $i--) { $pts.Add((New-Object System.Drawing.PointF ($x + $w * $i / $steps), ($y + $h - $rnd.Next(0, [int]($h * .18))))) }
  for ($i = 5; $i -ge 0; $i--) { $pts.Add((New-Object System.Drawing.PointF ($x + $rnd.Next(0, [int]($w * .04))), ($y + $h * $i / 5))) }
  $path = New-Object System.Drawing.Drawing2D.GraphicsPath
  $path.AddPolygon($pts.ToArray()); return $path
}
function Parchment($g, $paper, $x, $y, $w, $h) {
  $tb = New-Object System.Drawing.TextureBrush $paper; $tb.TranslateTransform($x, $y)
  $g.FillRectangle($tb, $x, $y, $w, $h)
  $g.FillRectangle((Brush '#EDDCB2' 205), $x, $y, $w, $h)
  foreach ($i in 0..9) { $g.DrawRectangle((Pen '#5C4020' 2 (60 - $i * 6)), $x + $i, $y + $i, $w - 2 * $i, $h - 2 * $i) }
  $g.DrawRectangle((Pen '#3A2A18' 1.5), $x, $y, $w, $h)
}
function Faded($g, $img, $src, $dst, $fadeLeft, $fadeRight, $bg) {
  $g.DrawImage($img, $dst, $src, [System.Drawing.GraphicsUnit]::Pixel)
  if ($fadeLeft -gt 0) {
    $r = Rect $dst.X $dst.Y $fadeLeft $dst.Height
    $lg = New-Object System.Drawing.Drawing2D.LinearGradientBrush $r, (Col $bg 255), (Col $bg 0), 0.0
    $g.FillRectangle($lg, $dst.X, $dst.Y, $fadeLeft + 1, $dst.Height)
  }
  if ($fadeRight -gt 0) {
    $r = Rect ($dst.Right - $fadeRight) $dst.Y $fadeRight $dst.Height
    $lg = New-Object System.Drawing.Drawing2D.LinearGradientBrush $r, (Col $bg 0), (Col $bg 255), 0.0
    $g.FillRectangle($lg, $dst.Right - $fadeRight, $dst.Y, $fadeRight, $dst.Height)
  }
}
# Redness becomes blueness (k = 0.8): the attacker's red lion banner becomes the
# defender's blue one while greys and the gold lion keep their tone.
function Swapped($img) {
  $bmp = New-Object System.Drawing.Bitmap $img.Width, $img.Height
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $m = New-Object System.Drawing.Imaging.ColorMatrix
  $m.Matrix00 = 0.2; $m.Matrix10 = 0.8; $m.Matrix01 = 0.15; $m.Matrix11 = 0.85
  $m.Matrix02 = 0.8; $m.Matrix12 = -0.8; $m.Matrix22 = 1
  $ia = New-Object System.Drawing.Imaging.ImageAttributes; $ia.SetColorMatrix($m)
  $g.DrawImage($img, (New-Object System.Drawing.Rectangle 0, 0, $img.Width, $img.Height), 0, 0, $img.Width, $img.Height, 'Pixel', $ia)
  $g.Dispose(); return $bmp
}

$paper = Img 'paper.jpg'; $rail = Img 'rail.jpg'; $castle = Img 'panel.jpg'; $two = Img 'two.jpg'
$soldiers = Img 'head-left.jpg'; $keep = Img 'head-right.jpg'; $army = Img 'parch.jpg'

# ---- lobby_bg.png: 1240 x 720 ----
$W = 1240; $H = 720
$bmp, $g = Canvas $W $H
$g.FillRectangle((Brush '#0E1013'), 0, 0, $W, $H)
# header band
Faded $g $soldiers (Rect 0 0 138 124) (Rect 24 0 250 118) 0 90 '#0E1013'
Faded $g $keep (Rect 0 4 190 116) (Rect 966 0 260 118) 110 0 '#0E1013'
$titleFont = New-Object System.Drawing.Font $cinzel, 56, ([System.Drawing.FontStyle]1), ([System.Drawing.GraphicsUnit]::Pixel)
$tw = $g.MeasureString('CRUSADER WARS', $titleFont).Width
$tx = ($W - $tw - 50) / 2
Text $g 'CRUSADER WARS' $cinzel 56 1 '#E6CF97' $tx 6 ($tw + 4) 78
$g.DrawImage($two, (Rect ($tx + $tw - 8) 4 58 84))
Text $g 'CK3  BATTLE  BRIDGE' $cinzel 17 0 '#D8CBAE' 0 80 1240 28 'Center'
$g.DrawLine((Pen '#8C6D38' 1), 40, 122, 1200, 122); $g.DrawLine((Pen '#8C6D38' 1), 40, 125, 1200, 125)
# three parchment columns
Parchment $g $paper 22 130 434 482
Parchment $g $paper 470 130 300 482
Parchment $g $paper 784 130 434 482
foreach ($side in @(@{x = 22; label = 'ATTACKER'; ribbon = '#9B221B'; seed = 3; banner = $rail },
                    @{x = 784; label = 'DEFENDER'; ribbon = '#243449'; seed = 7; banner = (Swapped $rail) })) {
  $x = $side.x
  $g.FillPath((Brush $side.ribbon), (BrushPath ($x + 70) 136 294 38 $side.seed))
  Text $g $side.label $cinzel 20 1 '#F4E9CE' ($x + 70) 136 294 38 'Center'
  # banner emblem in a gold frame (in place of a CK3 portrait, which the save does not carry)
  $g.DrawImage($side.banner, (Rect ($x + 14) 184 136 190), (Rect 0 10 180 250), [System.Drawing.GraphicsUnit]::Pixel)
  $g.DrawRectangle((Pen '#8C6D38' 3), $x + 14, 184, 136, 190); $g.DrawRectangle((Pen '#3A2A18' 1), $x + 19, 189, 126, 180)
  Text $g 'Martial' $crimson 19 0 '#3A2A1C' ($x + 196) 228 120 28
  Text $g 'Prowess' $crimson 19 0 '#3A2A1C' ($x + 196) 260 120 28
  $g.DrawLine((Pen '#9C8A6A' 1), $x + 170, 258, $x + 420, 258); $g.DrawLine((Pen '#9C8A6A' 1), $x + 170, 290, $x + 420, 290)
  Text $g 'men in CK3' $crimson 15 2 '#5A4A36' ($x + 330) 306 90 30 'Far'
  Text $g 'THREE KINGDOMS UNITS' $crimson 13 1 '#5A4A36' ($x + 22) 382 250 22
  Text $g 'MEN' $crimson 13 1 '#5A4A36' ($x + 330) 382 86 22 'Far'
  $g.DrawLine((Pen '#7A6446' 1.5), $x + 18, 404, $x + 418, 404)
  foreach ($i in 1..6) { $g.DrawLine((Pen '#A8977A' 1), $x + 18, 404 + $i * 32, $x + 418, 404 + $i * 32) }
}
# centre column: landscape, date/season, roll plate
Faded $g $castle (Rect 0 40 282 150) (Rect 484 184 272 110) 0 0 '#E8D8B6'
$g.DrawRectangle((Pen '#6E5B36' 1.5), 484, 184, 272, 110)
Text $g 'Date' $crimson 15 0 '#5A4A36' 484 298 134 22 'Center'
Text $g 'Season' $crimson 15 0 '#5A4A36' 622 298 134 22 'Center'
$g.DrawLine((Pen '#9C8A6A' 1), 620, 300, 620, 350)
Text $g 'ROLL' $cinzel 16 1 '#3A2A1C' 470 356 300 26 'Center'
$g.FillPath((Brush '#1A1714'), (BrushPath 500 384 240 60 11))
$g.DrawLine((Pen '#7A6446' 1), 490, 612, 750, 612)
# footer
$g.FillRectangle((Brush '#0B0D10'), 0, 618, $W, 102)
$g.DrawLine((Pen '#8C6D38' 1), 22, 618, 1218, 618)
# outer frame
$g.DrawRectangle((Pen '#8C6D38' 2), 3, 3, $W - 7, $H - 7); $g.DrawRectangle((Pen '#3A3226' 1), 8, 8, $W - 17, $H - 17)
$bmp.Save((Join-Path $out 'lobby_bg.png'), [System.Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $bmp.Dispose()

# ---- button plates (the game draws the labels) ----
function Plate($name, $w, $h, $fill, $edge, $seed, $torn) {
  $bmp, $g = Canvas $w $h
  if ($torn) { $p = BrushPath 2 2 ($w - 4) ($h - 4) $seed; $g.FillPath((Brush $fill), $p); $g.DrawPath((Pen $edge 1.5 160), $p) }
  else {
    $g.FillRectangle((Brush $fill), 2, 2, $w - 4, $h - 4)
    $g.DrawRectangle((Pen $edge 1.5), 2, 2, $w - 5, $h - 5); $g.DrawRectangle((Pen $edge 1 90), 6, 6, $w - 13, $h - 13)
  }
  $bmp.Save((Join-Path $out $name), [System.Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $bmp.Dispose()
}
Plate 'plate.png' 240 40 '#1C1B18' '#BDA77B' 0 $false
Plate 'plate_hover.png' 240 40 '#7D1A14' '#E2C57F' 0 $false
Plate 'fight.png' 270 64 '#9B221B' '#E2C57F' 21 $true
Plate 'fight_hover.png' 270 64 '#BE2F24' '#F4DDA0' 21 $true
# the screen dim behind the lobby (stretched to the screen by the layout)
$bmp, $g = Canvas 16 16
$g.FillRectangle((Brush '#05070A' 170), 0, 0, 16, 16)
$bmp.Save((Join-Path $out 'dim.png'), [System.Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $bmp.Dispose()
Get-ChildItem $out | Select-Object Name, Length
