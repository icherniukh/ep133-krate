/// MIDIBridge — CoreMIDI wrapper callable from Python via rubicon-objc.

#import <Foundation/Foundation.h>
#import <CoreMIDI/CoreMIDI.h>

NS_ASSUME_NONNULL_BEGIN

@interface MIDIBridge : NSObject

/// Discover available MIDI devices.
/// Returns NSArray of NSDictionary with keys: name, hasInput, hasOutput.
- (NSArray<NSDictionary *> *)discoverDevices;

/// Connect to a named device (matches source + destination by name).
/// Sends are routed to the matched destination; receives come from the matched source.
/// Returns YES on success.
- (BOOL)connectToDevice:(NSString *)deviceName;

/// Disconnect from the current device.
- (void)disconnect;

/// Send raw SysEx bytes (including F0 and F7 framing).
/// Internally strips F0/F7, fragments into UMP SysEx7, sends via MIDISendEventList.
/// Returns YES on success.
- (BOOL)sendSysEx:(NSData *)data;

/// Drain all received SysEx messages since the last call.
/// Returns NSArray of NSData, each containing a complete SysEx message (with F0/F7).
/// Thread-safe: the receive callback buffers messages; this method atomically drains them.
- (NSArray<NSData *> *)drainReceivedMessages;

/// Whether a device is currently connected with output capability.
@property (nonatomic, readonly) BOOL isConnected;

/// Name of the currently connected device (nil if not connected).
@property (nonatomic, readonly, nullable) NSString *connectedDeviceName;

@end

NS_ASSUME_NONNULL_END
