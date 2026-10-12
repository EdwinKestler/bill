#pragma once

#include <BLEAdvertisedDevice.h>
#include <BLECharacteristic.h>
#include <BLEClient.h>
#include <BLERemoteCharacteristic.h>
#include <BLEServer.h>
#include <ChunkProtocol.h>
#include <FS.h>
#include <TapProtocol.h>
#include <cstddef>
#include <cstdint>
#include <string>

#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

class TapGatt {
 public:
  static constexpr char OUTBOUND_PATH[] = "/tap-out.ready";
  static constexpr char INBOUND_PATH[] = "/tap-in.ready";

  struct InboundTransfer {
    uint8_t kind = 0;
    uint32_t sessionId = 0;
    size_t size = 0;
    char path[32] = {};
  };

  TapGatt();
  void begin(BLEServer* server);
  void poll();
  bool canStageOutbound() const;
  bool stageOutbound(uint8_t kind, uint32_t sessionId, size_t size,
                     const char* path);
  bool peekInboundTransfer(InboundTransfer& transfer);
  void discardStaged();
  bool takeStatusUpdate(char* status, size_t statusSize);

 private:
  class ControlCallbacks : public BLECharacteristicCallbacks {
   public:
    explicit ControlCallbacks(TapGatt& owner) : owner_(owner) {}
    void onWrite(BLECharacteristic* characteristic) override;
   private:
    TapGatt& owner_;
  };
  class ChunkCallbacks : public BLECharacteristicCallbacks {
   public:
    explicit ChunkCallbacks(TapGatt& owner) : owner_(owner) {}
    void onWrite(BLECharacteristic* characteristic) override;
   private:
    TapGatt& owner_;
  };
  class ScanCallbacks : public BLEAdvertisedDeviceCallbacks {
   public:
    explicit ScanCallbacks(TapGatt& owner) : owner_(owner) {}
    void onResult(BLEAdvertisedDevice device) override;
   private:
    TapGatt& owner_;
  };
  class ClientCallbacks : public BLEClientCallbacks {
   public:
    explicit ClientCallbacks(TapGatt& owner) : owner_(owner) {}
    void onConnect(BLEClient*) override {}
    void onDisconnect(BLEClient*) override;
   private:
    TapGatt& owner_;
  };

  void handleControl(const std::string& encoded);
  void handleSenderChunk(const std::string& encoded);
  void handleAdvertised(BLEAdvertisedDevice& device);
  void handleClientDisconnect();
  void handleReceiverChunk(uint8_t* data, size_t length);
  bool connectReceiver(const char* address, esp_ble_addr_type_t addressType,
                       int rssi);
  bool startSenderLocked();
  void pollSenderLocked(uint32_t now);
  void finishSenderLocked(bool success);
  void resetReceiverLocked(bool removeReady);
  void queueReceiverAckLocked(const rgbbill::chunk::FrameView& frame,
                              rgbbill::chunk::Result result);
  void updateMetadataLocked();
  void setStatus(const char* status);

  BLEServer* server_ = nullptr;
  BLECharacteristic* metadataCharacteristic_ = nullptr;
  BLECharacteristic* tapChunkOutCharacteristic_ = nullptr;
  ControlCallbacks controlCallbacks_;
  ChunkCallbacks chunkCallbacks_;
  ScanCallbacks scanCallbacks_;
  ClientCallbacks clientCallbacks_;
  mutable SemaphoreHandle_t mutex_ = nullptr;
  bool storageReady_ = false;

  rgbbill::tap::Gate gate_;
  rgbbill::tap::OneShotArm receiverArm_;
  bool scanning_ = false;
  bool connectRequested_ = false;
  char observedAddress_[18] = {};
  uint32_t observedLogAtMs_ = 0;
  char candidateAddress_[18] = {};
  esp_ble_addr_type_t candidateAddressType_ = BLE_ADDR_TYPE_PUBLIC;
  int candidateRssi_ = -127;

  BLEClient* client_ = nullptr;
  BLERemoteCharacteristic* remoteControl_ = nullptr;
  BLERemoteCharacteristic* remoteChunkIn_ = nullptr;
  BLERemoteCharacteristic* remoteChunkOut_ = nullptr;
  bool receiverConnected_ = false;
  bool receiverDisconnectAfterAck_ = false;
  rgbbill::tap::Metadata expectedMetadata_;
  rgbbill::chunk::ReceiveSession receiverSession_;
  File receiverFile_;
  bool inboundReady_ = false;
  uint8_t inboundKind_ = 0;
  uint32_t inboundSessionId_ = 0;
  size_t inboundSize_ = 0;
  uint32_t receiverLastFrameCrc_ = 0;
  bool receiverAckPending_ = false;
  uint8_t receiverAck_[rgbbill::chunk::MAX_FRAME_SIZE] = {};
  size_t receiverAckLength_ = 0;

  bool outboundReady_ = false;
  uint8_t outboundKind_ = 0;
  uint32_t outboundSessionId_ = 0;
  size_t outboundSize_ = 0;
  File outboundFile_;
  bool outboundActive_ = false;
  bool outboundWaitingAck_ = false;
  uint16_t outboundSequence_ = 0;
  uint16_t outboundTotal_ = 0;
  uint8_t outboundRetries_ = 0;
  uint32_t outboundSentAtMs_ = 0;
  uint8_t outboundEncoded_[rgbbill::chunk::MAX_FRAME_SIZE] = {};
  size_t outboundEncodedLength_ = 0;
  bool serverWasConnected_ = false;

  portMUX_TYPE statusMux_ = portMUX_INITIALIZER_UNLOCKED;
  char status_[16] = {};
  bool statusDirty_ = false;
};
