import untangle
import struct
from datetime import datetime
from pypacker.layer12 import ethernet
from pypacker.layer3 import ip
#from pypacker.layer567 import smb
import smbHeader

# grab the latest fingerprint files:
# wget chatteronthewire.org/download/updates/satori/fingerprints/tcp.xml -O tcp.xml
#
# looking for new fingerprints
# python3 satori.py > output.txt
# cat output.txt | awk -F';' '{print $3, $4, $5, $6, $7}' | sort -u > output2.txt
#

# 
# while I'd like to build this one out, it requires using the sequence of previous ones to compare to current to see if it is a factor of "blah" (256 for example).
# as I'm not tracking stuf in this version of Satori, for now this module will not be completed, but it is at least started.
#

def networkByteOrder(data):  #use struct to handle this instead!
  list = []
  val = hex(data).strip("0x")
  print(data)
  print(val)
  for i in range(0, len(val), 2):
    list.insert(0,val[i:i+2])
  return(list)

def parseBuffer(buf, unicode):
  val = ''
  if unicode == False:
    for i in range(0, len(buf)):
      if buf[i] == 0:
        val = val + ','
      else:
        val = val + chr(buf[i])
  else:
    for i in range(0, len(buf), 2):
      if buf[i] == 0:
        val = val + ','
      else:
        val = val + chr(buf[i])

  return(val)

def smbTCPProcess(eth, ts, nativeExactList, lanmanExactList, nativePartialList, lanmanPartialList):
  ip4 = eth.upper_layer
  tcp1 = ip4.upper_layer
  #need to take tcp1.body_bytes and shove the info into stuff now......
  x = len(smbHeader.netbiosSessionService())
  if len(tcp1.body_bytes) >= x:
    nbss1 = smbHeader.netbiosSessionService(tcp1.body_bytes)
    smb1 = smbHeader.tcpSMB(nbss1.body_bytes)
    if smb1.proto == 0xFF534D42:
      if smb1.cmd == 0x73:  #may look at others later, but for now, this is the only one of use for fingerprinting
        flags2 = struct.unpack('@H',smb1.flags2)[0]
        if "{0:>16b}".format(flags2)[0] == '1':  #probably a better way to do this with bit shifting, but this works for now  *in pascal had:  (_tcp_smb.flags2 and 32768)
          unicode=True
        else:  #0 or space 
          unicode=False

        nativeOS = ''
        nativeLanMan = ''

        if smb1.body_bytes[0] == 0X0:
          pass
        elif smb1.body_bytes[0] == 0X3:
          SS1 = smbHeader.SSAndRequestHeader_w3(smb1.body_bytes)
          if len(SS1.body_bytes) % 2 == 0:
            buffer = SS1.body_bytes[1:]
          else:
            buffer = SS1.body_bytes
          #Native OS; Native LAN Manager; Primary Domain
          info = parseBuffer(buffer, unicode)
          info = info.split(',')
          nativeOS = info[0]
          nativeLanMan = info[1]
          primaryDomain = info[2]
        elif smb1.body_bytes[0] == 0X4:
          SS1 = smbHeader.SSAndRequestHeader_w4(smb1.body_bytes)
          x = struct.unpack('@h',SS1.SecurityBlobLen)[0]
          securityBlob = SS1.body_bytes[0:x]
          if x % 2 == 0:
            buffer = SS1.body_bytes[x+1:]
          else:
            buffer = SS1.body_bytes[x:]
          #Native OS; Native LAN Manager
          info = parseBuffer(buffer, unicode)
          info = info.split(',')
          nativeOS = info[0]
          nativeLanMan = info[1]
        elif smb1.body_bytes[0] == 0XC:
          SS1 = smbHeader.SSAndRequestHeader_w12(smb1.body_bytes)
          x = struct.unpack('@h',SS1.SecurityBlobLen)[0]
          securityBlob = SS1.body_bytes[0:x]
          if x % 2 == 0:
            buffer = SS1.body_bytes[x+1:]
          else:
            buffer = SS1.body_bytes[x:]
          #Native OS; Native LAN Manager
          info = parseBuffer(buffer, unicode)
          info = info.split(',')
          nativeOS = info[0]
          nativeLanMan = info[1]
        elif smb1.body_bytes[0] == 0XD:
          SS1 = smbHeader.SSAndRequestHeader_w13(smb1.body_bytes)
          buffer = SS1.body_bytes
          #Account; Primary Domain; Native OS; Native LAN Manager
          ansi = struct.unpack('@h',SS1.ANSIPasswordLen)[0]
          uni = struct.unpack('@h',SS1.UniCodePassLen)[0]
          info = parseBuffer(buffer[ansi + uni:], unicode)
          info = info.split(',')
          nativeOS = info[2]
          nativeLanMan = info[3]


        timeStamp = datetime.utcfromtimestamp(ts).isoformat()

        if nativeOS != '':
          osGuess = SMBTCPFingerprintLookup(nativeExactList, nativePartialList, nativeOS)
          print("%s;%s;%s;SMBNATIVE;%s;%s" % (timeStamp,eth[ethernet.Ethernet].src_s, eth[ip.IP].src_s, nativeOS, osGuess))
        if nativeLanMan != '':
          osGuess = SMBTCPFingerprintLookup(lanmanExactList, lanmanPartialList, nativeLanMan)
          print("%s;%s;%s;SMBNATIVE;%s;%s" % (timeStamp,eth[ethernet.Ethernet].src_s, eth[ip.IP].src_s, nativeLanMan, osGuess))




def BuildSMBTCPFingerprintFiles():
  # converting from the xml format to a more flat format that will hopefully be faster than walking the entire xml every FP lookup
  nativeExactList = {}
  nativePartialList = {}
  lanmanExactList = {}
  lanmanPartialList = {}

  obj = untangle.parse('fingerprints/smb.xml')
  fingerprintsCount = len(obj.SMB.fingerprints)
  for x in range(0,fingerprintsCount):
    os = obj.SMB.fingerprints.fingerprint[x]['name']
    testsCount = len(obj.SMB.fingerprints.fingerprint[x].smb_tests)
    test = {}
    for y in range(0,testsCount):
      test = obj.SMB.fingerprints.fingerprint[x].smb_tests.test[y]
      if test is None:  #if testsCount = 1, then untangle doesn't allow us to iterate through it
        test = obj.SMB.fingerprints.fingerprint[x].smb_tests.test
      weight = test['weight']
      matchtype = test['matchtype']
      smbnativename = test['smbnativename']
      smbnativelanman = test['smbnativelanman']
      if matchtype == 'exact':
        if smbnativename != None:
          if smbnativename in nativeExactList:
            oldValue = nativeExactList.get(smbnativename)
            nativeExactList[smbnativename] = oldValue + '|' + os + ':' + weight
          else:
            nativeExactList[smbnativename] = os + ':' + weight
        elif smbnativelanman != None:
          if smbnativelanman in lanmanExactList:
            oldValue = lanmanExactList.get(smbnativelanman)
            lanmanExactList[smbnativelanman] = oldValue + '|' + os + ':' + weight
          else:
            lanmanExactList[smbnativelanman] = os + ':' + weight

      else:
        if smbnativename != None:
          if smbnativename in nativePartialList:
            oldValue = nativePartialList.get(smbnativename)
            nativePartialList[smbnativename] = oldValue + '|' + os + ':' + weight
          else:
            nativePartialList[smbnativename] = os + ':' + weight
        elif smbnativelanman != None:
          if smbnativelanman in lanmanPartialList:
            oldValue = lanmanPartialList.get(smbnativelanman)
            lanmanPartialList[smbnativelanman] = oldValue + '|' + os + ':' + weight
          else:
            lanmanPartialList[smbnativelanman] = os + ':' + weight

  return [nativeExactList, lanmanExactList, nativePartialList, lanmanPartialList]



def SMBTCPFingerprintLookup(exactList, partialList, value):
  #same as DHCP one, may be able to look at combining in the future?
  exactValue = ''
  partialValue = ''

  if value in exactList:
    exactValue = exactList.get(value)

  for key, val in partialList.items():
    if value.find(key) > -1:
      partialValue = partialValue + '|' + val

  if partialValue.startswith('|'):
    partialValue = partialValue[1:]
  if partialValue.endswith('|'):
    partialValue = partialValue[:-1]

  fingerprint = exactValue + '|' + partialValue
  if fingerprint.startswith('|'):
    fingerprint = fingerprint[1:]
  if fingerprint.endswith('|'):
    fingerprint = fingerprint[:-1]

  return fingerprint




