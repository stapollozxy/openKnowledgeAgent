#import <Foundation/Foundation.h>
#import <Vision/Vision.h>

static void Emit(NSString *text, NSString *error) {
    NSDictionary *payload = @{ @"text": text ?: @"", @"error": error ?: @"" };
    NSData *data = [NSJSONSerialization dataWithJSONObject:payload options:0 error:nil];
    [[NSFileHandle fileHandleWithStandardOutput] writeData:data];
    [[NSFileHandle fileHandleWithStandardOutput] writeData:[@"\n" dataUsingEncoding:NSUTF8StringEncoding]];
}

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        if (argc != 2) {
            Emit(@"", @"Expected one image path.");
            return 2;
        }
        NSString *path = [NSString stringWithUTF8String:argv[1]];
        if (![[NSFileManager defaultManager] fileExistsAtPath:path]) {
            Emit(@"", @"The pasted image file does not exist.");
            return 3;
        }

        __block NSArray<VNRecognizedTextObservation *> *observations = @[];
        __block NSError *recognitionError = nil;
        VNRecognizeTextRequest *request = [[VNRecognizeTextRequest alloc]
            initWithCompletionHandler:^(VNRequest *finished, NSError *error) {
                recognitionError = error;
                observations = (NSArray<VNRecognizedTextObservation *> *)finished.results ?: @[];
            }];
        request.recognitionLevel = VNRequestTextRecognitionLevelAccurate;
        request.usesLanguageCorrection = YES;
        request.automaticallyDetectsLanguage = YES;

        VNImageRequestHandler *handler = [[VNImageRequestHandler alloc]
            initWithURL:[NSURL fileURLWithPath:path] options:@{}];
        NSError *performError = nil;
        if (![handler performRequests:@[request] error:&performError] || recognitionError) {
            NSError *error = recognitionError ?: performError;
            Emit(@"", error.localizedDescription ?: @"Image text recognition failed.");
            return 4;
        }

        NSMutableArray<NSString *> *lines = [NSMutableArray array];
        for (VNRecognizedTextObservation *observation in observations) {
            VNRecognizedText *candidate = [[observation topCandidates:1] firstObject];
            if (candidate.string.length) [lines addObject:candidate.string];
        }
        Emit([lines componentsJoinedByString:@"\n"], @"");
    }
    return 0;
}
