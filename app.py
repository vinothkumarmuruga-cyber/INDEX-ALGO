// This Pine Script™ code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/
// © vinothkumarmurugauhb0s

//@version=6
indicator("Nifty_PE_ITM_BEP", overlay = false)

// ===== INPUTS =====
symbol      = str.upper(input.string("NIFTY","SYMBOL"))
expiryDate  = input.string("260901","EXPIRY YYMMDD")
strikePrice = str.tostring(input.float(24250 ,"CANDLE PLOT", step=50))

openStrike = input.int(24250, "OPEN STRIKE", step = 50)


// ===== SYMBOL BUILD =====
strikecall = symbol + expiryDate + "C" + strikePrice
strikeput  = symbol + expiryDate + "P" + strikePrice


// ===== SYMBOL BUILD BEP STRIKE =====

bepstrikecall1 = symbol + expiryDate + "C" + str.tostring(openStrike - 50)
bepstrikeput1  = symbol + expiryDate + "C" + str.tostring(openStrike + 50)

bepstrikecall2 = symbol + expiryDate + "C" + str.tostring(openStrike - 100)
bepstrikeput2  = symbol + expiryDate + "C" + str.tostring(openStrike + 100)

bepstrikecall3 = symbol + expiryDate + "C" + str.tostring(openStrike - 150)
bepstrikeput3  = symbol + expiryDate + "C" + str.tostring(openStrike + 150)

bepstrikecall4 = symbol + expiryDate + "C" + str.tostring(openStrike - 200)
bepstrikeput4 = symbol + expiryDate + "C" +str.tostring(openStrike + 200)

// bepstrikecall5 = symbol + expiryDate + "C" + str.tostring(openStrike - 50)
// bepstrikeput5  = symbol + expiryDate + "P" + str.tostring(openStrike + 50)

// bepstrikecall6 = symbol + expiryDate + "C" + str.tostring(openStrike - 100)
// bepstrikeput6  = symbol + expiryDate + "P" + str.tostring(openStrike + 100)

// bepstrikecall7 = symbol + expiryDate + "C" + str.tostring(openStrike - 150)
// bepstrikeput7  = symbol + expiryDate + "P" + str.tostring(openStrike + 150)

// bepstrikecall8 = symbol + expiryDate + "C" + str.tostring(openStrike - 200)
// bepstrikeput8  = symbol + expiryDate + "P" + str.tostring(openStrike + 200)

//////////////////////////// candle plot //////////////////////////////////
[openCall,highCall,lowCall,closeCall] = request.security(strikecall , "" ,[open,high,low,close])
[openPut,highPut,lowPut,closePut] = request.security(strikeput , "" ,[open,high,low,close])

//  Define the colors for bullish and bearish candles based on the close vs open price
call_candle_color = closeCall > openCall ? color.new(color.blue, 0) : color.new(color.black, 0)
Put_candle_color = closePut > openPut ? color.new(color.green, 0) : color.new(color.red, 0)

// You can use a similar conditional for the wick and border colors
call_wick_color = closeCall > openCall ? color.new(color.blue, 0) : color.new(color.black, 0)
call_border_color = closeCall > openCall ? color.new(color.blue, 0) : color.new(color.black, 0)


Put_wick_color = closePut > openPut ? color.new(color.green, 0) : color.new(color.red, 0)
Put_border_color = closePut > openPut ? color.new(color.green, 0) : color.new(color.red, 0)

// Plot the call candles with the dynamic colors
// plotcandle(openCall, highCall, lowCall, closeCall, color=call_candle_color, wickcolor=call_wick_color, bordercolor=call_border_color)
plotcandle(openPut, highPut, lowPut, closePut, color=Put_candle_color, wickcolor=Put_wick_color, bordercolor=Put_border_color)


//////// Dyanmic BEP ///////////////
BEP = (closeCall+closePut)/2

// plot(BEP , "BEP" , color=color.fuchsia , linewidth = 1)

////////////////////// pc bep ////////////////
PC_CE = request.security(strikecall , "D" ,close)
PC_PE = request.security(strikeput , "D" ,close)

PC_BEP = (PC_CE+PC_PE)/2

// plot(PC_BEP , "PC_BEP" , color=color.aqua , linewidth = 2)

//////////////////// BEP for Strike ///////////////

bep_CE = request.security(strikecall , "" ,close)
bep_PE = request.security(strikeput , "" ,close)

bep_CE1 = request.security(bepstrikecall1 , "" ,close)
bep_PE1 = request.security(bepstrikeput1 , "" ,close)

bep_CE2 = request.security(bepstrikecall2 , "" ,close)
bep_PE2 = request.security(bepstrikeput2 , "" ,close)

bep_CE3 = request.security(bepstrikecall3 , "" ,close)
bep_PE3 = request.security(bepstrikeput3 , "" ,close)

bep_CE4 = request.security(bepstrikecall4 , "" ,close)
bep_PE4 = request.security(bepstrikeput4 , "" ,close)

////////////// Dynamic BEP ////////////

strangle_bep = (closeCall + bep_PE) / 2

////////////// ITM PE BEP ////////////

strangle_bep1 = (closePut + bep_CE1) / 2
strangle_bep2 = (closePut + bep_CE2) / 2
strangle_bep3 = (closePut + bep_CE3) / 2
strangle_bep4 = (closePut + bep_CE4) / 2

////////////// ITM CE BEP ////////////

strangle_bep5 = (closePut + bep_PE1) / 2
strangle_bep6 = (closePut + bep_PE2) / 2
strangle_bep7 = (closePut + bep_PE3) / 2
strangle_bep8 = (closePut + bep_PE4) / 2

plot(strangle_bep , "BEP STRIKE" , color=color.fuchsia , linewidth = 2)

////////////// ITM PE BEP ////////////

plot(strangle_bep1 , "PE-1" , color=color.red , linewidth = 1)
plot(strangle_bep2 , "PE-2" , color=color.red , linewidth = 1)
plot(strangle_bep3 , "PE-3" , color=color.red , linewidth = 1)
plot(strangle_bep4 , "PE-4" , color=color.red , linewidth = 1)

////////////// ITM CE BEP ////////////

plot(strangle_bep5 , "CE-1" , color=color.green , linewidth = 1)
plot(strangle_bep6 , "CE-2" , color=color.green , linewidth = 1)
plot(strangle_bep7 , "CE-3" , color=color.green , linewidth = 1)
plot(strangle_bep8 , "CE-4" , color=color.green , linewidth = 1)


//////////////////////
count = ta.barssince(session.isfirstbar)

isExtend = input.bool(true, "Extend")

var barCount = 0

if session.islastbar
    barCount := count
plot(count , color = color.yellow, display = display.status_line)


var line PC_BEP_line = na


var label PC_BEP_label = na





if session.isfirstbar
    PC_BEP_line := line.new(bar_index, PC_BEP, bar_index + barCount, PC_BEP, color=color.aqua, width=2)

// //     if not isHist
//         line.delete(PC_BEP_line[1])

//     // PC_BEP_label := label.new(bar_index, PC_BEP, "PC_BEP:" + str.tostring(PC_BEP, format.mintick), style=label.style_label_right, text_formatting=text.format_bold, color=color.new(color.yellow, 50), textcolor=color.black)


// ===================================================================
// =====================  ENTRY / TARGET / SL  ======================
// ===================================================================
// Logic (as requested):
//   Entry  -> Put candle closes ABOVE any of the 9 plotted BEP lines
//             (BEP STRIKE, PE-1..4, CE-1..4), checked on a fixed
//             "entry timeframe" candle (default 3 min) regardless of
//             the chart's own timeframe.
//   Target -> the NEXT line above the entry price, i.e. the lowest of
//             the 9 current line values that sits above the entry
//             price (since the 9 lines are independent levels, not a
//             fixed ladder, "next line" is resolved dynamically each
//             time an entry triggers).
//   SL     -> the LOW of that same entry candle. Trade is closed out
//             (marked SL Hit) if a later entry-timeframe candle's low
//             trades at/through that level before target is reached.
// Assumption: target is considered hit on a HIGH touch of the target
// level, SL is considered hit on a LOW touch of the SL level. Adjust
// the two conditions below if you want close-based exits instead.
// ===================================================================

// ----- inputs -----
entryTF      = input.timeframe("3", "Entry Timeframe")
showTable    = input.bool(true, "Show Entry/Target/SL Table")
tablePos     = input.string("top_right", "Table Position", options=["top_right","top_left","bottom_right","bottom_left"])

// ----- entry-timeframe Put candle (close, low, high, time), independent of chart TF -----
[closeEntry, lowEntry, highEntry, timeEntry] = request.security(strikeput, entryTF, [close, low, high, time], lookahead=barmerge.lookahead_off)

// ----- crossover of the entry-TF close above each of the 9 lines -----
crossBEP = ta.crossover(closeEntry, strangle_bep)
crossPE1 = ta.crossover(closeEntry, strangle_bep1)
crossPE2 = ta.crossover(closeEntry, strangle_bep2)
crossPE3 = ta.crossover(closeEntry, strangle_bep3)
crossPE4 = ta.crossover(closeEntry, strangle_bep4)
crossCE1 = ta.crossover(closeEntry, strangle_bep5)
crossCE2 = ta.crossover(closeEntry, strangle_bep6)
crossCE3 = ta.crossover(closeEntry, strangle_bep7)
crossCE4 = ta.crossover(closeEntry, strangle_bep8)

anyCross = crossBEP or crossPE1 or crossPE2 or crossPE3 or crossPE4 or crossCE1 or crossCE2 or crossCE3 or crossCE4

crossedLineName = crossBEP ? "BEP STRIKE" : crossPE1 ? "PE-1" : crossPE2 ? "PE-2" : crossPE3 ? "PE-3" : crossPE4 ? "PE-4" : crossCE1 ? "CE-1" : crossCE2 ? "CE-2" : crossCE3 ? "CE-3" : crossCE4 ? "CE-4" : na

// ----- find the nearest line value above the entry price -----
f_nextAbove(_price) =>
    float _best = na
    float _v0 = strangle_bep
    float _v1 = strangle_bep1
    float _v2 = strangle_bep2
    float _v3 = strangle_bep3
    float _v4 = strangle_bep4
    float _v5 = strangle_bep5
    float _v6 = strangle_bep6
    float _v7 = strangle_bep7
    float _v8 = strangle_bep8
    if _v0 > _price and (na(_best) or _v0 < _best)
        _best := _v0
    if _v1 > _price and (na(_best) or _v1 < _best)
        _best := _v1
    if _v2 > _price and (na(_best) or _v2 < _best)
        _best := _v2
    if _v3 > _price and (na(_best) or _v3 < _best)
        _best := _v3
    if _v4 > _price and (na(_best) or _v4 < _best)
        _best := _v4
    if _v5 > _price and (na(_best) or _v5 < _best)
        _best := _v5
    if _v6 > _price and (na(_best) or _v6 < _best)
        _best := _v6
    if _v7 > _price and (na(_best) or _v7 < _best)
        _best := _v7
    if _v8 > _price and (na(_best) or _v8 < _best)
        _best := _v8
    _best

// ----- trade journal (persists across bars, one row per trade) -----
maxRows = input.int(20, "Max Rows in Journal (most recent)", minval=1, maxval=200)

var float[]  jTime    = array.new_float()   // entry bar time (entry-TF candle)
var string[] jLine    = array.new_string()  // line that was crossed
var float[]  jEntry   = array.new_float()
var float[]  jTarget  = array.new_float()
var float[]  jSL      = array.new_float()
var float[]  jExit    = array.new_float()   // na while still open
var string[] jResult  = array.new_string()  // "In Trade" / "Target Hit" / "SL Hit"

// Indices (into the j* arrays above) of ALL trades currently open at once.
// A cross-and-close of ANY line is its own independent signal -- it is no
// longer gated on being flat, so price grinding up through several lines
// opens several trades in parallel, each with its own target/SL.
var int[] openIdxs = array.new_int()

// ----- 1. check every currently-open trade for SL/Target on this bar -----
if array.size(openIdxs) > 0
    for i = array.size(openIdxs) - 1 to 0
        idx         = array.get(openIdxs, i)
        slLevel     = array.get(jSL, idx)
        targetLevel = array.get(jTarget, idx)
        if not na(slLevel) and lowEntry <= slLevel
            array.set(jExit, idx, lowEntry)
            array.set(jResult, idx, "SL Hit")
            array.remove(openIdxs, i)
        else if not na(targetLevel) and highEntry >= targetLevel
            array.set(jExit, idx, highEntry)
            array.set(jResult, idx, "Target Hit")
            array.remove(openIdxs, i)

// ----- 2. open a new trade on every fresh line cross+close, regardless of
//          how many other trades are already open -----
isNewEntry = anyCross

if isNewEntry
    array.push(jTime, timeEntry)
    array.push(jLine, crossedLineName)
    array.push(jEntry, closeEntry)
    array.push(jTarget, f_nextAbove(closeEntry))
    array.push(jSL, lowEntry)
    array.push(jExit, na)
    array.push(jResult, "In Trade")
    array.push(openIdxs, array.size(jEntry) - 1)

    // trim oldest rows once the journal grows past maxRows
    if array.size(jEntry) > maxRows
        array.shift(jTime)
        array.shift(jLine)
        array.shift(jEntry)
        array.shift(jTarget)
        array.shift(jSL)
        array.shift(jExit)
        array.shift(jResult)
        // every stored index shifts down by 1; drop the one that fell off
        for i = array.size(openIdxs) - 1 to 0
            v = array.get(openIdxs, i) - 1
            if v < 0
                array.remove(openIdxs, i)
            else
                array.set(openIdxs, i, v)

// ----- marker on the entry-TF crossover bar -----
plotshape(isNewEntry, title="Entry", style=shape.triangleup, location=location.belowbar, color=color.lime, size=size.small)

// ----- journal table (grows one row per trade, newest on top) -----
tablePosition = tablePos == "top_right" ? position.top_right : tablePos == "top_left" ? position.top_left : tablePos == "bottom_right" ? position.bottom_right : position.bottom_left

var table journalTable = na

if showTable and barstate.islast
    if not na(journalTable)
        table.delete(journalTable)

    n = array.size(jEntry)
    journalTable := table.new(tablePosition, 7, n + 1, border_width=1)

    table.cell(journalTable, 0, 0, "Time", bgcolor=color.gray, text_color=color.white)
    table.cell(journalTable, 1, 0, "Line", bgcolor=color.gray, text_color=color.white)
    table.cell(journalTable, 2, 0, "Entry", bgcolor=color.gray, text_color=color.white)
    table.cell(journalTable, 3, 0, "Target", bgcolor=color.gray, text_color=color.white)
    table.cell(journalTable, 4, 0, "SL", bgcolor=color.gray, text_color=color.white)
    table.cell(journalTable, 5, 0, "Exit", bgcolor=color.gray, text_color=color.white)
    table.cell(journalTable, 6, 0, "Result", bgcolor=color.gray, text_color=color.white)

    for i = 0 to n - 1
        row = n - i                      // newest trade on top
        idx = n - 1 - i
        result = array.get(jResult, idx)
        rowColor = result == "In Trade" ? color.new(color.yellow, 70) : result == "Target Hit" ? color.new(color.green, 70) : color.new(color.red, 70)
        exitVal = array.get(jExit, idx)

        table.cell(journalTable, 0, row, str.format_time(array.get(jTime, idx), "HH:mm", "Asia/Kolkata"), bgcolor=rowColor)
        table.cell(journalTable, 1, row, array.get(jLine, idx), bgcolor=rowColor)
        table.cell(journalTable, 2, row, str.tostring(array.get(jEntry, idx), format.mintick), bgcolor=rowColor)
        table.cell(journalTable, 3, row, str.tostring(array.get(jTarget, idx), format.mintick), bgcolor=rowColor)
        table.cell(journalTable, 4, row, str.tostring(array.get(jSL, idx), format.mintick), bgcolor=rowColor)
        table.cell(journalTable, 5, row, na(exitVal) ? "-" : str.tostring(exitVal, format.mintick), bgcolor=rowColor)
        table.cell(journalTable, 6, row, result, bgcolor=rowColor)
