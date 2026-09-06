package core

import (
	"bytes"
	"reflect"
	"testing"
)

func TestUDPMessageWireRoundTrip(t *testing.T) {
	want := udpMessage{SessionID: 0x01020304, Host: "example.com", Port: 53, MsgID: 7, FragCount: 1, Data: []byte{0x12, 0x34, 0x01, 0x00}}
	wire := want.Pack()
	if !bytes.HasPrefix(wire, []byte{1, 2, 3, 4}) {
		t.Fatal("packet must begin with session ID, without zero padding")
	}
	var got udpMessage
	if err := got.Unpack(wire); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("round trip: got %+v, want %+v", got, want)
	}
}
