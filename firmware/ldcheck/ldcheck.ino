__attribute__((__section__(".noinit"))) unsigned long noinitTest[2];
void setup() { noinitTest[0] = 1; }
void loop() {}
