// HUDLocate: asks macOS for the current location once, reverse-geocodes
// the city and writes ~/Library/Application Support/DesktopHUD/location.json.
// Launched by the HUD daemon with `open -g -j -W`. Exits on its own.
#import <CoreLocation/CoreLocation.h>
#import <Foundation/Foundation.h>

@interface Locator : NSObject <CLLocationManagerDelegate>
@property(strong) CLLocationManager *manager;
@property(strong) CLGeocoder *geocoder;
@property BOOL done;
@end

@implementation Locator
- (void)start {
    self.manager = [CLLocationManager new];
    self.geocoder = [CLGeocoder new];
    self.manager.delegate = self;
    self.manager.desiredAccuracy = kCLLocationAccuracyKilometer;
    CLAuthorizationStatus s = self.manager.authorizationStatus;
    if (s == kCLAuthorizationStatusNotDetermined) [self.manager requestWhenInUseAuthorization];
    else if (s == kCLAuthorizationStatusDenied || s == kCLAuthorizationStatusRestricted) [self finish:nil city:nil];
    else [self.manager requestLocation];
}
- (void)locationManagerDidChangeAuthorization:(CLLocationManager *)m {
    CLAuthorizationStatus s = m.authorizationStatus;
    if (s == kCLAuthorizationStatusAuthorizedAlways) [m requestLocation];
    else if (s == kCLAuthorizationStatusDenied || s == kCLAuthorizationStatusRestricted) [self finish:nil city:nil];
}
- (void)locationManager:(CLLocationManager *)m didUpdateLocations:(NSArray<CLLocation *> *)locs {
    CLLocation *loc = locs.lastObject;
    if (!loc) return;
    [self.geocoder reverseGeocodeLocation:loc completionHandler:^(NSArray<CLPlacemark *> *marks, NSError *e) {
        CLPlacemark *p = marks.firstObject;
        [self finish:loc city:(p.locality ?: p.administrativeArea)];
    }];
}
- (void)locationManager:(CLLocationManager *)m didFailWithError:(NSError *)error { [self finish:nil city:nil]; }
- (void)finish:(CLLocation *)loc city:(NSString *)city {
    if (self.done) return;
    self.done = YES;
    if (loc) {
        NSString *path = [NSHomeDirectory() stringByAppendingPathComponent:
                          @"Library/Application Support/DesktopHUD/location.json"];
        NSDictionary *obj = @{@"lat": @(loc.coordinate.latitude), @"lon": @(loc.coordinate.longitude),
                              @"city": city ?: @"", @"source": @"macos",
                              @"time": @([[NSDate date] timeIntervalSince1970])};
        NSData *data = [NSJSONSerialization dataWithJSONObject:obj options:0 error:nil];
        [data writeToFile:path atomically:YES];
    }
    exit(0);
}
@end

int main(void) {
    @autoreleasepool {
        Locator *l = [Locator new];
        [l start];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 45 * NSEC_PER_SEC), dispatch_get_main_queue(), ^{
            [l finish:nil city:nil];
        });
        [[NSRunLoop mainRunLoop] run];
    }
    return 0;
}
