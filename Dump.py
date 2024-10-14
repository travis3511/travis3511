import hashlib
class Dump:
  def __init__(self,file):
    self.id = None
    self.encoding = open(file).encoding
    self.mode = open(file).mode
    self.data = None
    self.bytes = None
    self.name = open(file).name
  def read(self):
    with open(self.name) as r:
      self.data = r.read() 
      self.bytes = self.data.encode()
  def write(self,text):
    with open(self.name,"w") as r:
      r.write(text)
      
