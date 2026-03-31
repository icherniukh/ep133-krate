/// MIDIBridge.m — CoreMIDI lifecycle, UMP SysEx7 send/receive.

#import "MIDIBridge.h"
#import <os/log.h>

static os_log_t _midiLog(void) {
    static os_log_t log;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        log = os_log_create("com.ep133.krate", "MIDIBridge");
    });
    return log;
}

// ------------------------------------------------------------------
// MARK: - Private interface
// ------------------------------------------------------------------

@interface MIDIBridge () {
    MIDIClientRef   _client;
    MIDIPortRef     _inputPort;
    MIDIPortRef     _outputPort;

    MIDIEndpointRef _connectedSource;
    MIDIEndpointRef _connectedDest;

    NSMutableArray<NSData *> *_receiveBuffer;
    NSLock *_bufferLock;

    NSMutableData *_sysExAccumulator;
}
@end

// ------------------------------------------------------------------
// MARK: - Implementation
// ------------------------------------------------------------------

@implementation MIDIBridge

- (instancetype)init {
    self = [super init];
    if (self) {
        _receiveBuffer = [NSMutableArray new];
        _bufferLock = [NSLock new];
        _sysExAccumulator = [NSMutableData new];

        _connectedSource = 0;
        _connectedDest = 0;

        [self _setupMIDI];
    }
    return self;
}

- (void)dealloc {
    [self disconnect];
    if (_inputPort)  MIDIPortDispose(_inputPort);
    if (_outputPort) MIDIPortDispose(_outputPort);
    if (_client)     MIDIClientDispose(_client);
}

// ------------------------------------------------------------------
// MARK: - Setup
// ------------------------------------------------------------------

- (void)_setupMIDI {
    __weak MIDIBridge *weakSelf = self;

    OSStatus status = MIDIClientCreateWithBlock(
        CFSTR("KrateMIDIBridge"),
        &_client,
        ^(const MIDINotification *notification) {
            MIDINotificationMessageID msgID = notification->messageID;
            if (msgID == kMIDIMsgObjectAdded ||
                msgID == kMIDIMsgObjectRemoved ||
                msgID == kMIDIMsgSetupChanged) {
                os_log_info(_midiLog(), "MIDI setup changed (id=%d)", (int)msgID);
                (void)weakSelf;
            }
        }
    );
    if (status != noErr) {
        os_log_error(_midiLog(), "MIDIClientCreateWithBlock failed: %d", (int)status);
        return;
    }

    status = MIDIInputPortCreateWithProtocol(
        _client,
        CFSTR("KrateInput"),
        kMIDIProtocol_1_0,
        &_inputPort,
        ^(const MIDIEventList *eventList, void *srcConnRefCon) {
            MIDIBridge *strongSelf = weakSelf;
            if (strongSelf) {
                [strongSelf _handleIncomingEvents:eventList];
            }
        }
    );
    if (status != noErr) {
        os_log_error(_midiLog(), "MIDIInputPortCreateWithProtocol failed: %d", (int)status);
    }

    status = MIDIOutputPortCreate(_client, CFSTR("KrateOutput"), &_outputPort);
    if (status != noErr) {
        os_log_error(_midiLog(), "MIDIOutputPortCreate failed: %d", (int)status);
    }
}

// ------------------------------------------------------------------
// MARK: - Device Discovery
// ------------------------------------------------------------------

static NSString *EndpointName(MIDIEndpointRef ep) {
    CFStringRef name = NULL;
    MIDIObjectGetStringProperty(ep, kMIDIPropertyName, &name);
    if (name) {
        return (__bridge_transfer NSString *)name;
    }
    return @"Unknown";
}

static BOOL IsNetworkSession(NSString *name) {
    return [name isEqualToString:@"Session 1"] ||
           [name isEqualToString:@"Network Session 1"];
}

- (NSArray<NSDictionary *> *)discoverDevices {
    NSMutableDictionary<NSString *, NSNumber *> *sourcesByName = [NSMutableDictionary new];
    for (ItemCount i = 0; i < MIDIGetNumberOfSources(); i++) {
        MIDIEndpointRef ep = MIDIGetSource(i);
        NSString *name = EndpointName(ep);
        sourcesByName[name] = @(ep);
    }

    NSMutableDictionary<NSString *, NSNumber *> *destsByName = [NSMutableDictionary new];
    for (ItemCount i = 0; i < MIDIGetNumberOfDestinations(); i++) {
        MIDIEndpointRef ep = MIDIGetDestination(i);
        NSString *name = EndpointName(ep);
        destsByName[name] = @(ep);
    }

    NSMutableSet<NSString *> *seen = [NSMutableSet new];
    NSMutableArray<NSDictionary *> *devices = [NSMutableArray new];

    NSMutableArray<NSString *> *allNames = [NSMutableArray new];
    [allNames addObjectsFromArray:sourcesByName.allKeys];
    [allNames addObjectsFromArray:destsByName.allKeys];

    for (NSString *name in allNames) {
        if (name.length == 0 || IsNetworkSession(name) || [seen containsObject:name]) {
            continue;
        }
        [seen addObject:name];

        BOOL hasInput  = sourcesByName[name] != nil;
        BOOL hasOutput = destsByName[name] != nil;

        [devices addObject:@{
            @"name":      name,
            @"hasInput":  @(hasInput),
            @"hasOutput": @(hasOutput),
            @"sourceRef": sourcesByName[name] ?: @(0),
            @"destRef":   destsByName[name] ?: @(0),
        }];
    }

    os_log_info(_midiLog(), "Discovered %lu MIDI device(s)", (unsigned long)devices.count);
    return [devices copy];
}

// ------------------------------------------------------------------
// MARK: - Connect / Disconnect
// ------------------------------------------------------------------

- (BOOL)connectToDevice:(NSString *)deviceName {
    [self disconnect];
    MIDIEndpointRef source = 0, dest = 0;

    for (ItemCount i = 0; i < MIDIGetNumberOfSources(); i++) {
        MIDIEndpointRef ep = MIDIGetSource(i);
        if ([EndpointName(ep) isEqualToString:deviceName]) {
            source = ep;
            break;
        }
    }

    for (ItemCount i = 0; i < MIDIGetNumberOfDestinations(); i++) {
        MIDIEndpointRef ep = MIDIGetDestination(i);
        if ([EndpointName(ep) isEqualToString:deviceName]) {
            dest = ep;
            break;
        }
    }

    if (dest == 0) {
        os_log_error(_midiLog(), "No destination found for '%{public}@'", deviceName);
        return NO;
    }

    if (source != 0 && _inputPort != 0) {
        OSStatus status = MIDIPortConnectSource(_inputPort, source, NULL);
        if (status != noErr) {
            os_log_error(_midiLog(), "MIDIPortConnectSource failed: %d", (int)status);
        } else {
            _connectedSource = source;
        }
    }

    _connectedDest = dest;
    _connectedDeviceName = [deviceName copy];

    os_log_info(_midiLog(), "Connected to '%{public}@' (src=%u, dst=%u)",
                deviceName, (unsigned)source, (unsigned)dest);
    return YES;
}

- (void)disconnect {
    if (_connectedSource != 0 && _inputPort != 0) {
        MIDIPortDisconnectSource(_inputPort, _connectedSource);
    }
    _connectedSource = 0;
    _connectedDest = 0;
    _connectedDeviceName = nil;

    [_bufferLock lock];
    [_receiveBuffer removeAllObjects];
    [_bufferLock unlock];

    [_sysExAccumulator setLength:0];
}

- (BOOL)isConnected {
    return _connectedDest != 0;
}

// ------------------------------------------------------------------
// MARK: - Send
// ------------------------------------------------------------------

- (BOOL)sendSysEx:(NSData *)data {
    if (_connectedDest == 0 || _outputPort == 0) {
        os_log_error(_midiLog(), "sendSysEx: not connected");
        return NO;
    }

    const uint8_t *bytes = data.bytes;
    NSUInteger length = data.length;
    if (length < 2) return NO;

    NSUInteger start = 0, end = length;
    if (bytes[0] == 0xF0) start = 1;
    if (bytes[length - 1] == 0xF7) end = length - 1;
    NSUInteger payloadLen = end - start;

    NSUInteger numChunks = (payloadLen == 0) ? 1 : (payloadLen + 5) / 6;
    uint32_t umpWords[numChunks * 2];
    NSUInteger offset = start;

    for (NSUInteger i = 0; i < numChunks; i++) {
        NSUInteger chunkStart = offset;
        NSUInteger chunkLen = MIN(6, end - offset);

        uint8_t statusNibble;
        if (numChunks == 1) {
            statusNibble = 0x0;
        } else if (i == 0) {
            statusNibble = 0x1;
        } else if (i == numChunks - 1) {
            statusNibble = 0x3;
        } else {
            statusNibble = 0x2;
        }

        uint8_t b[6] = {0, 0, 0, 0, 0, 0};
        for (NSUInteger j = 0; j < chunkLen; j++) {
            b[j] = bytes[chunkStart + j];
        }

        uint32_t word1 = (0x3u << 28)
                       | (0x0u << 24)
                       | ((uint32_t)statusNibble << 20)
                       | ((uint32_t)chunkLen << 16)
                       | ((uint32_t)b[0] << 8)
                       | (uint32_t)b[1];

        uint32_t word2 = ((uint32_t)b[2] << 24)
                       | ((uint32_t)b[3] << 16)
                       | ((uint32_t)b[4] << 8)
                       | (uint32_t)b[5];

        umpWords[i * 2]     = word1;
        umpWords[i * 2 + 1] = word2;
        offset += chunkLen;
    }

    MIDIEventList eventList;
    MIDIEventPacket *packet = MIDIEventListInit(&eventList, kMIDIProtocol_1_0);

    for (NSUInteger i = 0; i < numChunks; i++) {
        uint32_t words[2] = { umpWords[i * 2], umpWords[i * 2 + 1] };
        packet = MIDIEventListAdd(&eventList,
                                  sizeof(MIDIEventList),
                                  packet,
                                  0,
                                  2,
                                  words);
        if (packet == NULL) {
            os_log_error(_midiLog(), "MIDIEventListAdd failed at chunk %lu", (unsigned long)i);
            return NO;
        }
    }

    OSStatus sendStatus = MIDISendEventList(_outputPort, _connectedDest, &eventList);
    if (sendStatus != noErr) {
        os_log_error(_midiLog(), "MIDISendEventList failed: %d", (int)sendStatus);
        return NO;
    }

    os_log_debug(_midiLog(), "Sent %lu bytes via %lu UMP packet(s)",
                 (unsigned long)length, (unsigned long)numChunks);
    return YES;
}

// ------------------------------------------------------------------
// MARK: - Receive
// ------------------------------------------------------------------

- (NSArray<NSData *> *)drainReceivedMessages {
    [_bufferLock lock];
    NSArray<NSData *> *messages = [_receiveBuffer copy];
    [_receiveBuffer removeAllObjects];
    [_bufferLock unlock];
    return messages;
}

- (void)_handleIncomingEvents:(const MIDIEventList *)eventList {
    const MIDIEventPacket *packet = &eventList->packet[0];
    for (UInt32 p = 0; p < eventList->numPackets; p++) {
        UInt32 wordCount = packet->wordCount;
        const UInt32 *words = packet->words;

        NSUInteger i = 0;
        while (i < wordCount) {
            UInt32 word = words[i];
            UInt32 msgType = (word >> 28) & 0x0F;

            if (msgType == 0x3) {
                UInt32 statusNibble = (word >> 20) & 0x0F;
                UInt32 numBytes = (word >> 16) & 0x0F;
                UInt32 w2 = (i + 1 < wordCount) ? words[i + 1] : 0;

                uint8_t chunk[6];
                NSUInteger chunkLen = 0;
                if (numBytes > 0) chunk[chunkLen++] = (word >> 8) & 0xFF;
                if (numBytes > 1) chunk[chunkLen++] = word & 0xFF;
                if (numBytes > 2) chunk[chunkLen++] = (w2 >> 24) & 0xFF;
                if (numBytes > 3) chunk[chunkLen++] = (w2 >> 16) & 0xFF;
                if (numBytes > 4) chunk[chunkLen++] = (w2 >> 8) & 0xFF;
                if (numBytes > 5) chunk[chunkLen++] = w2 & 0xFF;

                switch (statusNibble) {
                    case 0x0: {
                        NSMutableData *msg = [NSMutableData dataWithBytes:(uint8_t[]){0xF0} length:1];
                        [msg appendBytes:chunk length:chunkLen];
                        [msg appendBytes:(uint8_t[]){0xF7} length:1];
                        [self _bufferReceivedMessage:msg];
                        break;
                    }
                    case 0x1: {
                        [_sysExAccumulator setLength:0];
                        [_sysExAccumulator appendBytes:chunk length:chunkLen];
                        break;
                    }
                    case 0x2: {
                        [_sysExAccumulator appendBytes:chunk length:chunkLen];
                        break;
                    }
                    case 0x3: {
                        [_sysExAccumulator appendBytes:chunk length:chunkLen];
                        NSMutableData *msg = [NSMutableData dataWithBytes:(uint8_t[]){0xF0} length:1];
                        [msg appendData:_sysExAccumulator];
                        [msg appendBytes:(uint8_t[]){0xF7} length:1];
                        [self _bufferReceivedMessage:msg];
                        [_sysExAccumulator setLength:0];
                        break;
                    }
                    default:
                        break;
                }
                i += 2;
            } else {
                i += 1;
            }
        }

        packet = (const MIDIEventPacket *)((const uint8_t *)packet +
                  offsetof(MIDIEventPacket, words) + packet->wordCount * sizeof(UInt32));
    }
}

- (void)_bufferReceivedMessage:(NSData *)message {
    [_bufferLock lock];
    [_receiveBuffer addObject:[message copy]];
    if (_receiveBuffer.count > 500) {
        [_receiveBuffer removeObjectAtIndex:0];
    }
    [_bufferLock unlock];

    os_log_debug(_midiLog(), "Buffered RX SysEx (%lu bytes)", (unsigned long)message.length);
}

@end
