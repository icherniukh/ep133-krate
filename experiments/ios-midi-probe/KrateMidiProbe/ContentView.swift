import SwiftUI
import CoreMIDI
import os.log

struct MidiLogEntry: Identifiable {
    let id = UUID()
    let timestamp: Date
    let type: LogType
    let title: String
    let hex: String
    let detail: String?
    
    enum LogType {
        case sent, received, info, error
    }
}

/// Pairs a MIDI source (input) and destination (output) that share the same name.
struct MidiDevice: Identifiable {
    let id = UUID()
    let name: String
    var source: MIDIEndpointRef
    var destination: MIDIEndpointRef
}

class MidiManager: ObservableObject {
    @Published var status = "Not connected"
    @Published var isConnected = false
    @Published var logEntries: [MidiLogEntry] = []
    @Published var devices: [MidiDevice] = []
    @Published var selectedDeviceIndex: Int? = nil
    
    private var client: MIDIClientRef = 0
    private var inputPort: MIDIPortRef = 0
    private var outputPort: MIDIPortRef = 0
    private var connectedSources: Set<MIDIEndpointRef> = []
    private var sequenceNumber: UInt8 = 0
    
    private let sysExGroup: UInt8 = 0 // UMP group 0
    
    private let logger = Logger(subsystem: "com.ep133.krate", category: "midi")
    
    var selectedDevice: MidiDevice? {
        guard let idx = selectedDeviceIndex, devices.indices.contains(idx) else { return nil }
        return devices[idx]
    }
    
    init() {
        setupMIDI()
    }
    
    // MARK: - Setup
    
    private func setupMIDI() {
        // Client with notification block for hotplug
        MIDIClientCreateWithBlock("Krate MIDI Probe" as CFString, &client) { [weak self] notification in
            let messageID = notification.pointee.messageID
            if messageID == .msgObjectAdded || messageID == .msgObjectRemoved || messageID == .msgSetupChanged {
                DispatchQueue.main.async { self?.refreshDevices() }
            }
        }
        
        // Input port — MIDI 1.0 protocol so we get classic byte-stream semantics
        MIDIInputPortCreateWithProtocol(
            client,
            "Krate Input" as CFString,
            ._1_0,
            &inputPort
        ) { [weak self] eventList, _ in
            self?.handleIncomingEvents(eventList)
        }
        
        MIDIOutputPortCreate(client, "Krate Output" as CFString, &outputPort)
        
        refreshDevices()
    }
    
    // MARK: - Device discovery
    
    func refreshDevices() {
        // Disconnect any previously connected sources
        for src in connectedSources {
            MIDIPortDisconnectSource(inputPort, src)
        }
        connectedSources.removeAll()
        
        // Build name→endpoint maps
        var sourcesByName: [String: MIDIEndpointRef] = [:]
        for i in 0..<MIDIGetNumberOfSources() {
            let ep = MIDIGetSource(i)
            sourcesByName[endpointName(ep)] = ep
        }
        
        var destsByName: [String: MIDIEndpointRef] = [:]
        for i in 0..<MIDIGetNumberOfDestinations() {
            let ep = MIDIGetDestination(i)
            destsByName[endpointName(ep)] = ep
        }
        
        // Merge into paired devices, filtering out MIDI Network Session virtual ports
        let networkSessionNames: Set<String> = ["Session 1", "Network Session 1"]
        var seen: Set<String> = []
        var found: [MidiDevice] = []
        for name in (Array(sourcesByName.keys) + Array(destsByName.keys)) {
            guard !name.isEmpty, !networkSessionNames.contains(name), seen.insert(name).inserted else { continue }
            found.append(MidiDevice(
                name: name,
                source: sourcesByName[name] ?? 0,
                destination: destsByName[name] ?? 0
            ))
        }
        
        devices = found
        
        // Auto-select first device whose name matches EP-133 / KO, or just the first one
        if selectedDeviceIndex == nil || !(devices.indices.contains(selectedDeviceIndex!)) {
            selectedDeviceIndex = devices.firstIndex { $0.name.contains("EP-133") || $0.name.contains("KO II") }
                ?? (devices.isEmpty ? nil : 0)
        }
        
        // Connect all sources so we see traffic from any device
        for device in devices where device.source != 0 {
            let status = MIDIPortConnectSource(inputPort, device.source, nil)
            if status == noErr {
                connectedSources.insert(device.source)
            }
        }
        
        isConnected = selectedDevice?.destination != 0
        status = isConnected
            ? "Connected: \(selectedDevice?.name ?? "")"
            : (devices.isEmpty ? "No MIDI devices" : "No output on selected device")
        
        let srcCount = connectedSources.count
        let dstCount = devices.filter { $0.destination != 0 }.count
        addLog(.info, "Scan complete", detail: "\(devices.count) device(s), \(srcCount) src, \(dstCount) dst")
        
        // Log all raw endpoints for debugging
        for i in 0..<MIDIGetNumberOfSources() {
            let ep = MIDIGetSource(i)
            var uid: Int32 = 0
            MIDIObjectGetIntegerProperty(ep, kMIDIPropertyUniqueID, &uid)
            addLog(.info, "Source: \(endpointName(ep))", detail: "uid=\(uid) ref=\(ep)")
        }
        for i in 0..<MIDIGetNumberOfDestinations() {
            let ep = MIDIGetDestination(i)
            var uid: Int32 = 0
            MIDIObjectGetIntegerProperty(ep, kMIDIPropertyUniqueID, &uid)
            addLog(.info, "Dest: \(endpointName(ep))", detail: "uid=\(uid) ref=\(ep)")
        }
    }
    
    // MARK: - Protocol constants
    
    /// Teenage Engineering manufacturer ID + EP-133 device family
    private static let teHeader: [UInt8] = [0x00, 0x20, 0x76, 0x33, 0x40]
    
    /// Packed7: encode raw bytes for TE wire format.
    /// Every 7 input bytes become 8 output bytes (1 flags byte + 7 data bytes with MSB stripped).
    private static func packed7(_ data: [UInt8]) -> [UInt8] {
        var result: [UInt8] = []
        var i = 0
        while i < data.count {
            let chunkEnd = min(i + 7, data.count)
            var flags: UInt8 = 0
            var encoded: [UInt8] = []
            for j in i..<chunkEnd {
                if data[j] & 0x80 != 0 {
                    flags |= UInt8(1 << (j - i))
                }
                encoded.append(data[j] & 0x7F)
            }
            result.append(flags)
            result.append(contentsOf: encoded)
            i = chunkEnd
        }
        return result
    }
    
    /// Packed7: decode wire bytes back to raw bytes.
    private static func unpack7(_ data: [UInt8]) -> [UInt8] {
        var result: [UInt8] = []
        var i = 0
        while i < data.count {
            let flags = data[i]
            i += 1
            for bit in 0..<7 {
                guard i < data.count else { break }
                let msb: UInt8 = ((flags >> bit) & 1) << 7
                result.append((data[i] & 0x7F) | msb)
                i += 1
            }
        }
        return result
    }
    
    // MARK: - Send
    
    /// Sends the 3-step initialization handshake (matches Python client exactly).
    func initialize() {
        guard let dest = selectedDevice?.destination, dest != 0 else {
            addLog(.error, "No MIDI destination available")
            return
        }
        
        // Step 1: Universal MIDI Device Identity Request
        let msg1: [UInt8] = [0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7]
        addLog(.sent, "Identity Request", hex: msg1.map { String(format: "%02X", $0) }.joined(separator: " "))
        sendSysExBytes(msg1, to: dest)
        
        // Step 2: TE INIT 1
        let msg2: [UInt8] = [0xF0] + Self.teHeader + [0x61, 0x17, 0x01, 0xF7]
        addLog(.sent, "INIT 1", hex: msg2.map { String(format: "%02X", $0) }.joined(separator: " "))
        sendSysExBytes(msg2, to: dest)
        
        // Step 3: TE INIT 2
        let msg3: [UInt8] = [0xF0] + Self.teHeader + [0x61, 0x18, 0x05, 0x00, 0x01, 0x01, 0x00, 0x40, 0x00, 0x00, 0xF7]
        addLog(.sent, "INIT 2", hex: msg3.map { String(format: "%02X", $0) }.joined(separator: " "))
        sendSysExBytes(msg3, to: dest)
    }
    
    /// Sends a raw TE SysEx command (no 7-bit packing — just header + payload bytes).
    func sendTeCommand(_ payload: [UInt8]) {
        guard let dest = selectedDevice?.destination, dest != 0 else {
            addLog(.error, "No MIDI destination available")
            return
        }
        
        let sysex: [UInt8] = [0xF0] + Self.teHeader + payload + [0xF7]
        let hexString = sysex.map { String(format: "%02X", $0) }.joined(separator: " ")
        addLog(.sent, "Sent TE cmd", hex: hexString)
        sendSysExBytes(sysex, to: dest)
    }
    
    /// Sends a TE file operation command with packed7-encoded payload.
    /// Message format: F0 [teHeader] [opcode] [seq] 05 [packed7(rawPayload)] F7
    func sendFileCommand(opcode: UInt8, rawPayload: [UInt8]) {
        guard let dest = selectedDevice?.destination, dest != 0 else {
            addLog(.error, "No MIDI destination available")
            return
        }
        
        sequenceNumber = (sequenceNumber + 1) % 128
        let packed = Self.packed7(rawPayload)
        let sysex: [UInt8] = [0xF0] + Self.teHeader + [opcode, sequenceNumber, 0x05] + packed + [0xF7]
        let hexString = sysex.map { String(format: "%02X", $0) }.joined(separator: " ")
        addLog(.sent, "TX FileCmd", hex: hexString, detail: "op=0x\(String(opcode, radix: 16)) seq=\(sequenceNumber) raw=\(rawPayload.map { String(format: "%02X", $0) }.joined())")
        sendSysExBytes(sysex, to: dest)
    }
    
    /// Trigger on-device playback of a sample slot (audition).
    /// Sends AuditionRequest: opcode=0x6A, fileOp=PLAYBACK(0x05), action=0x01
    func playSlot(_ slot: Int) {
        let slotHi = UInt8((slot >> 8) & 0xFF)
        let slotLo = UInt8(slot & 0xFF)
        let rawPayload: [UInt8] = [
            0x05,                               // FileOp.PLAYBACK
            0x01,                               // action = play
            slotHi, slotLo,                     // slot (BE16)
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, // padding (6 bytes)
            0x03, 0xE8                          // parent_node = 1000 (BE16)
        ]
        addLog(.info, "Play slot \(slot)", detail: "raw=\(rawPayload.map { String(format: "%02X", $0) }.joined())")
        sendFileCommand(opcode: 0x6A, rawPayload: rawPayload)
    }
    
    func sendRawSysEx(_ bytes: [UInt8]) {
        guard let dest = selectedDevice?.destination, dest != 0 else {
            addLog(.error, "No MIDI destination available")
            return
        }
        
        let hexString = bytes.map { String(format: "%02X", $0) }.joined(separator: " ")
        addLog(.sent, "Sent raw SysEx", hex: hexString, detail: "\(bytes.count) bytes")
        
        sendSysExBytes(bytes, to: dest)
    }
    
    /// Sends SysEx bytes via MIDISendEventList using UMP SysEx7 fragmentation.
    /// Each UMP SysEx7 message (message type 0x3) carries up to 6 payload bytes
    /// in a 64-bit (2-word) packet. Multi-packet SysEx uses status nibbles:
    ///   0x0 = complete (fits in one packet)
    ///   0x1 = start, 0x2 = continue, 0x3 = end
    private func sendSysExBytes(_ bytes: [UInt8], to dest: MIDIEndpointRef) {
        // Strip F0/F7 framing — UMP SysEx7 doesn't include them
        var payload = bytes
        if payload.first == 0xF0 { payload.removeFirst() }
        if payload.last == 0xF7 { payload.removeLast() }
        
        // Fragment into chunks of 6 bytes max
        var chunks: [[UInt8]] = []
        var offset = 0
        while offset < payload.count {
            let end = min(offset + 6, payload.count)
            chunks.append(Array(payload[offset..<end]))
            offset = end
        }
        if chunks.isEmpty { chunks.append([]) }
        
        // Build UMP words — each SysEx7 fragment is 2 x UInt32
        var umpWords: [UInt32] = []
        for (i, chunk) in chunks.enumerated() {
            let status: UInt8
            if chunks.count == 1 {
                status = 0x0 // complete
            } else if i == 0 {
                status = 0x1 // start
            } else if i == chunks.count - 1 {
                status = 0x3 // end
            } else {
                status = 0x2 // continue
            }
            
            let numBytes = UInt8(chunk.count)
            // Pad chunk to 6 bytes
            var b = chunk
            while b.count < 6 { b.append(0) }
            
            // Word 1: [msgType 0x3 (4b)] [group (4b)] [status (4b)] [numBytes (4b)] [b0 (8b)] [b1 (8b)]
            let word1: UInt32 = (0x3 << 28)
                | (UInt32(sysExGroup) << 24)
                | (UInt32(status) << 20)
                | (UInt32(numBytes) << 16)
                | (UInt32(b[0]) << 8)
                | UInt32(b[1])
            
            // Word 2: [b2 (8b)] [b3 (8b)] [b4 (8b)] [b5 (8b)]
            let word2: UInt32 = (UInt32(b[2]) << 24)
                | (UInt32(b[3]) << 16)
                | (UInt32(b[4]) << 8)
                | UInt32(b[5])
            
            umpWords.append(word1)
            umpWords.append(word2)
        }
        
        // Build MIDIEventList and send
        var eventList = MIDIEventList()
        var packet = MIDIEventListInit(&eventList, ._1_0)
        
        // Add all SysEx fragments — each is 2 words
        for i in stride(from: 0, to: umpWords.count, by: 2) {
            var words = [umpWords[i], umpWords[i + 1]]
            packet = MIDIEventListAdd(&eventList, MemoryLayout<MIDIEventList>.size, packet, 0, 2, &words)
        }
        
        let sendStatus = MIDISendEventList(outputPort, dest, &eventList)
        if sendStatus != noErr {
            addLog(.error, "MIDISendEventList failed", detail: "OSStatus \(sendStatus)")
        } else {
            addLog(.info, "SysEx sent", detail: "\(bytes.count) bytes via \(chunks.count) UMP packet(s) to ref=\(dest)")
        }
    }
    
    // MARK: - Receive
    
    /// Accumulates SysEx bytes across multiple UMP packets (start/continue/end).
    private var sysExAccumulator: [UInt8] = []
    
    private func handleIncomingEvents(_ eventList: UnsafePointer<MIDIEventList>) {
        eventList.unsafeSequence().forEach { packet in
            let wordCount = Int(packet.pointee.wordCount)
            guard wordCount > 0 else { return }
            
            let words: [UInt32] = withUnsafePointer(to: packet.pointee.words) { ptr in
                ptr.withMemoryRebound(to: UInt32.self, capacity: wordCount) { buf in
                    Array(UnsafeBufferPointer(start: buf, count: wordCount))
                }
            }
            
            // Process words in pairs for SysEx7 (type 0x3) or singles for other types
            var i = 0
            while i < words.count {
                let word = words[i]
                let msgType = (word >> 28) & 0x0F
                
                switch msgType {
                case 0x2:
                    // MIDI 1.0 channel voice (1 word)
                    let status = UInt8((word >> 16) & 0xFF)
                    let d1 = UInt8((word >> 8) & 0xFF)
                    let d2 = UInt8(word & 0xFF)
                    let hex = String(format: "%02X %02X %02X", status, d1, d2)
                    addLog(.received, "RX Channel", hex: hex)
                    i += 1
                    
                case 0x3:
                    // SysEx7: always 2 words per fragment
                    let statusNibble = (word >> 20) & 0x0F
                    let numBytes = Int((word >> 16) & 0x0F)
                    let w2 = (i + 1 < words.count) ? words[i + 1] : 0
                    
                    // Extract up to 6 payload bytes from the word pair
                    var chunk: [UInt8] = []
                    if numBytes > 0 { chunk.append(UInt8((word >> 8) & 0xFF)) }
                    if numBytes > 1 { chunk.append(UInt8(word & 0xFF)) }
                    if numBytes > 2 { chunk.append(UInt8((w2 >> 24) & 0xFF)) }
                    if numBytes > 3 { chunk.append(UInt8((w2 >> 16) & 0xFF)) }
                    if numBytes > 4 { chunk.append(UInt8((w2 >> 8) & 0xFF)) }
                    if numBytes > 5 { chunk.append(UInt8(w2 & 0xFF)) }
                    
                    switch statusNibble {
                    case 0x0: // Complete (single-packet SysEx)
                        logReceivedSysEx(chunk)
                    case 0x1: // Start
                        sysExAccumulator = chunk
                    case 0x2: // Continue
                        sysExAccumulator.append(contentsOf: chunk)
                    case 0x3: // End
                        sysExAccumulator.append(contentsOf: chunk)
                        logReceivedSysEx(sysExAccumulator)
                        sysExAccumulator.removeAll()
                    default:
                        break
                    }
                    i += 2
                    
                default:
                    // Unknown — dump raw
                    let hex = String(format: "%08X", word)
                    addLog(.received, "RX Unknown", hex: hex)
                    i += 1
                }
            }
        }
    }
    
    /// Logs a complete reassembled SysEx message with TE protocol decoding.
    private func logReceivedSysEx(_ bytes: [UInt8]) {
        // Reconstruct full SysEx with F0/F7 for display
        let full = [0xF0] + bytes + [0xF7]
        let hex = full.map { String(format: "%02X", $0) }.joined(separator: " ")
        
        // Attempt to decode TE protocol messages
        let teHdr: [UInt8] = [0x00, 0x20, 0x76, 0x33, 0x40]
        if bytes.count >= 7, Array(bytes[0..<5]) == teHdr {
            let cmd = bytes[5]
            let seq = bytes[6]
            var detail = "cmd=0x\(String(format: "%02X", cmd)) seq=\(seq)"
            
            // If it's a file response (has 0x05 byte at offset 7), try to unpack
            if bytes.count > 8 && bytes[7] == 0x05 {
                let packedData = Array(bytes[8...])
                let raw = Self.unpack7(packedData)
                let rawHex = raw.map { String(format: "%02X", $0) }.joined(separator: " ")
                detail += " | unpacked: \(rawHex)"
            }
            
            addLog(.received, "RX SysEx (TE)", hex: hex, detail: detail)
        } else if bytes.count >= 4 && bytes[0] == 0x7E {
            // Universal MIDI identity response
            addLog(.received, "RX Identity Response", hex: hex, detail: "\(bytes.count) bytes")
        } else {
            addLog(.received, "RX SysEx", hex: hex, detail: "\(full.count) bytes")
        }
    }
    
    // MARK: - Helpers
    
    private func endpointName(_ endpoint: MIDIEndpointRef) -> String {
        var name: Unmanaged<CFString>?
        MIDIObjectGetStringProperty(endpoint, kMIDIPropertyName, &name)
        return (name?.takeRetainedValue() as String?) ?? "Unknown"
    }
    
    private func addLog(_ type: MidiLogEntry.LogType, _ title: String, hex: String = "", detail: String? = nil) {
        let entry = MidiLogEntry(
            timestamp: Date(),
            type: type,
            title: title,
            hex: hex,
            detail: detail
        )
        
        DispatchQueue.main.async {
            self.logEntries.insert(entry, at: 0)
            if self.logEntries.count > 200 {
                self.logEntries.removeLast()
            }
        }
    }
    
    func clearLog() {
        logEntries.removeAll()
    }
}

struct ContentView: View {
    @StateObject private var manager = MidiManager()
    
    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // Status + device picker header
                VStack(spacing: 8) {
                    HStack {
                        Circle()
                            .fill(manager.isConnected ? Color.green : Color.red)
                            .frame(width: 12, height: 12)
                        Text(manager.status)
                            .font(.subheadline)
                            .lineLimit(1)
                        Spacer()
                        Button("Refresh") {
                            manager.refreshDevices()
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }
                    
                    if !manager.devices.isEmpty {
                        Picker("Device", selection: Binding(
                            get: { manager.selectedDeviceIndex ?? 0 },
                            set: { manager.selectedDeviceIndex = $0; manager.refreshDevices() }
                        )) {
                            ForEach(Array(manager.devices.enumerated()), id: \.offset) { index, device in
                                HStack {
                                    Text(device.name)
                                    if device.source != 0 && device.destination != 0 {
                                        Text("I/O")
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                    } else if device.source != 0 {
                                        Text("IN")
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                    } else {
                                        Text("OUT")
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                .tag(index)
                            }
                        }
                        .pickerStyle(.menu)
                    }
                }
                .padding()
                .background(Color(.systemGray6))
                
                // Activity log
                List {
                    Section(header: Text("Activity Log")) {
                        if manager.logEntries.isEmpty {
                            Text("No activity yet.\nTap a button below to send MIDI commands.")
                                .foregroundColor(.secondary)
                                .italic()
                                .multilineTextAlignment(.center)
                        } else {
                            ForEach(manager.logEntries) { entry in
                                LogEntryRow(entry: entry)
                            }
                        }
                    }
                }
                .listStyle(.plain)
                
                // Action buttons
                VStack(spacing: 12) {
                    HStack(spacing: 12) {
                        Button("INIT Handshake") {
                            manager.initialize()
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(!manager.isConnected)
                        
                        Button("Play Slot 3") {
                            manager.playSlot(3)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.green)
                        .disabled(!manager.isConnected)
                    }
                    
                    HStack(spacing: 12) {
                        Button("Device Info") {
                            // 0x77 = INFO
                            manager.sendTeCommand([0x77])
                        }
                        .buttonStyle(.bordered)
                        .disabled(!manager.isConnected)
                        
                        Button("Clear Log", role: .destructive) {
                            manager.clearLog()
                        }
                        .buttonStyle(.bordered)
                    }
                }
                .padding(.vertical, 16)
            }
            .navigationTitle("Krate MIDI Probe")
        }
    }
}
struct LogEntryRow: View {
    let entry: MidiLogEntry
    
    var icon: String {
        switch entry.type {
        case .sent: return "arrow.right.circle.fill"
        case .received: return "arrow.left.circle.fill"
        case .info: return "info.circle.fill"
        case .error: return "exclamationmark.circle.fill"
        }
    }
    
    var iconColor: Color {
        switch entry.type {
        case .sent: return .blue
        case .received: return .green
        case .info: return .orange
        case .error: return .red
        }
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Image(systemName: icon)
                    .foregroundColor(iconColor)
                    .font(.caption)
                Text(entry.title)
                    .font(.subheadline)
                Spacer()
                Text(entry.timestamp, format: .dateTime.hour().minute().second())
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            
            if !entry.hex.isEmpty {
                Text(entry.hex)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.secondary)
                    .lineLimit(3)
            }
            
            if let detail = entry.detail {
                Text(detail)
                    .font(.caption2)
                    .foregroundColor(.indigo)
            }
        }
        .padding(.vertical, 2)
    }
}

