#import <AVFoundation/AVFoundation.h>
#import <Foundation/Foundation.h>
#import <Speech/Speech.h>
#import <signal.h>

static void Emit(NSString *type, NSString *text) {
    NSDictionary *payload = @{ @"type": type, @"text": text ?: @"" };
    NSData *data = [NSJSONSerialization dataWithJSONObject:payload options:0 error:nil];
    [[NSFileHandle fileHandleWithStandardOutput] writeData:data];
    [[NSFileHandle fileHandleWithStandardOutput] writeData:[@"\n" dataUsingEncoding:NSUTF8StringEncoding]];
}

@interface SpeechSession : NSObject
@property(nonatomic, strong) AVAudioEngine *engine;
@property(nonatomic, strong) SFSpeechAudioBufferRecognitionRequest *request;
@property(nonatomic, strong) SFSpeechRecognitionTask *task;
@property(nonatomic, copy) NSString *latest;
@property(nonatomic) BOOL stopping;
@property(nonatomic) BOOL finished;
- (void)authorizeAndStart:(NSString *)locale;
- (void)stop;
@end

@implementation SpeechSession

- (instancetype)init {
    if ((self = [super init])) {
        _engine = [[AVAudioEngine alloc] init];
        _latest = @"";
    }
    return self;
}

- (void)authorizeAndStart:(NSString *)locale {
    [SFSpeechRecognizer requestAuthorization:^(SFSpeechRecognizerAuthorizationStatus status) {
        dispatch_async(dispatch_get_main_queue(), ^{
            if (status != SFSpeechRecognizerAuthorizationStatusAuthorized) {
                Emit(@"error", @"Speech recognition permission was not granted in System Settings.");
                exit(2);
            }
            [self requestMicrophone:locale];
        });
    }];
}

- (void)requestMicrophone:(NSString *)locale {
    AVAuthorizationStatus status = [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio];
    if (status == AVAuthorizationStatusAuthorized) {
        [self start:locale];
    } else if (status == AVAuthorizationStatusNotDetermined) {
        [AVCaptureDevice requestAccessForMediaType:AVMediaTypeAudio completionHandler:^(BOOL granted) {
            dispatch_async(dispatch_get_main_queue(), ^{
                if (granted) [self start:locale];
                else {
                    Emit(@"error", @"Microphone permission was not granted in System Settings.");
                    exit(3);
                }
            });
        }];
    } else {
        Emit(@"error", @"Microphone permission is disabled in System Settings.");
        exit(3);
    }
}

- (void)start:(NSString *)locale {
    SFSpeechRecognizer *recognizer = [[SFSpeechRecognizer alloc] initWithLocale:[[NSLocale alloc] initWithLocaleIdentifier:locale]];
    if (!recognizer || !recognizer.available) {
        Emit(@"error", [NSString stringWithFormat:@"Apple Speech Recognition is unavailable for %@.", locale]);
        exit(4);
    }

    self.request = [[SFSpeechAudioBufferRecognitionRequest alloc] init];
    self.request.shouldReportPartialResults = YES;
    self.request.taskHint = SFSpeechRecognitionTaskHintDictation;
    if (recognizer.supportsOnDeviceRecognition) self.request.requiresOnDeviceRecognition = YES;

    AVAudioInputNode *input = self.engine.inputNode;
    AVAudioFormat *format = [input outputFormatForBus:0];
    [input installTapOnBus:0 bufferSize:1024 format:format block:^(AVAudioPCMBuffer *buffer, AVAudioTime *when) {
        [self.request appendAudioPCMBuffer:buffer];
    }];
    [self.engine prepare];
    NSError *engineError = nil;
    if (![self.engine startAndReturnError:&engineError]) {
        Emit(@"error", [NSString stringWithFormat:@"Could not start microphone capture: %@", engineError.localizedDescription]);
        exit(5);
    }

    self.task = [recognizer recognitionTaskWithRequest:self.request resultHandler:^(SFSpeechRecognitionResult *result, NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            if (result) {
                self.latest = result.bestTranscription.formattedString ?: @"";
                Emit(result.final ? @"final" : @"partial", self.latest);
                if (result.final) [self finish:0];
            } else if (error && !self.stopping) {
                Emit(@"error", [NSString stringWithFormat:@"Speech recognition failed: %@", error.localizedDescription]);
                [self finish:6];
            }
        });
    }];
    Emit(@"ready", @"");
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 60 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{ [self stop]; });
}

- (void)stop {
    if (self.stopping || self.finished) return;
    self.stopping = YES;
    [self.engine stop];
    [self.engine.inputNode removeTapOnBus:0];
    [self.request endAudio];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 4 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
        if (!self.finished) {
            if (self.latest.length) Emit(@"final", self.latest);
            else Emit(@"error", @"No speech was recognized. Try speaking closer to the microphone.");
            [self finish:self.latest.length ? 0 : 7];
        }
    });
}

- (void)finish:(int)code {
    if (self.finished) return;
    self.finished = YES;
    if (self.engine.running) [self.engine stop];
    [self.task cancel];
    exit(code);
}

@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        SpeechSession *session = [[SpeechSession alloc] init];
        signal(SIGINT, SIG_IGN);
        signal(SIGTERM, SIG_IGN);
        dispatch_source_t interruptSource = dispatch_source_create(DISPATCH_SOURCE_TYPE_SIGNAL, SIGINT, 0, dispatch_get_main_queue());
        dispatch_source_t terminateSource = dispatch_source_create(DISPATCH_SOURCE_TYPE_SIGNAL, SIGTERM, 0, dispatch_get_main_queue());
        dispatch_source_set_event_handler(interruptSource, ^{ [session stop]; });
        dispatch_source_set_event_handler(terminateSource, ^{ [session stop]; });
        dispatch_resume(interruptSource);
        dispatch_resume(terminateSource);
        NSString *locale = argc > 1 ? [NSString stringWithUTF8String:argv[1]] : @"zh-CN";
        [session authorizeAndStart:locale];
        [[NSRunLoop mainRunLoop] run];
    }
    return 0;
}
