import AppKit
let output = CommandLine.arguments[1]
let image = NSImage(size: NSSize(width: 1024, height: 1024))
image.lockFocus()
NSColor(red: 13/255, green: 20/255, blue: 27/255, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: 24,y: 24,width: 976,height: 976), xRadius: 220, yRadius: 220).fill()
let c = NSGraphicsContext.current!.cgContext
c.translateBy(x: 64, y: 960); c.scaleBy(x: 14, y: -14)
c.setFillColor(NSColor(red: 194/255, green: 160/255, blue: 255/255, alpha: 1).cgColor)
c.move(to: CGPoint(x:14,y:23)); c.addLine(to:CGPoint(x:9,y:6)); c.addQuadCurve(to:CGPoint(x:25,y:17), control:CGPoint(x:21,y:10)); c.addQuadCurve(to:CGPoint(x:39,y:17),control:CGPoint(x:32,y:14)); c.addQuadCurve(to:CGPoint(x:55,y:6),control:CGPoint(x:43,y:9));c.addLine(to:CGPoint(x:50,y:23));c.addCurve(to:CGPoint(x:51,y:47),control1:CGPoint(x:55,y:29),control2:CGPoint(x:56,y:39));c.addCurve(to:CGPoint(x:32,y:58),control1:CGPoint(x:47,y:54),control2:CGPoint(x:40,y:58));c.addCurve(to:CGPoint(x:13,y:47),control1:CGPoint(x:24,y:58),control2:CGPoint(x:17,y:54));c.addCurve(to:CGPoint(x:14,y:23),control1:CGPoint(x:8,y:39),control2:CGPoint(x:9,y:29));c.closePath();c.fillPath()
c.setFillColor(NSColor(red:13/255,green:19/255,blue:27/255,alpha:1).cgColor)
for points in [[CGPoint(x:20,y:29),CGPoint(x:29,y:34),CGPoint(x:21,y:36)],[CGPoint(x:44,y:29),CGPoint(x:35,y:34),CGPoint(x:43,y:36)]]{c.move(to:points[0]);c.addLines(between:Array(points.dropFirst()));c.closePath();c.fillPath()}
c.setStrokeColor(NSColor(red:13/255,green:19/255,blue:27/255,alpha:1).cgColor);c.setLineWidth(3);c.setLineCap(.round);c.move(to:CGPoint(x:22,y:43));c.addQuadCurve(to:CGPoint(x:42,y:43),control:CGPoint(x:32,y:51));c.strokePath()
image.unlockFocus()
let bitmap = NSBitmapImageRep(data:image.tiffRepresentation!)!
try bitmap.representation(using:.png,properties:[:])!.write(to:URL(fileURLWithPath:output))
