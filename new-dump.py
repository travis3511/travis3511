#!/usr/bin/env python3
import argparse
import os
from collections import Counter
import pandas as pd
from glob import glob
from ipaddress import ip_address

companyName = ''
defaultOutFile = "secretsdump-parsed"
nullNT = "31d6cfe0d16ae931b73c59d7e0c089c0"
nullNTpt = "N/A [Blank]"
extUniq = ".uniqhashes"
extTsv = ".tsv"
headNTDS = "User\tRID\tLM\tNT"
headNTDSStatus = "User\tRID\tLM\tNT\tReuse\tCracked\tMethod\tPlaintext\tLength\tBelowMinLen\tIsAdmin\tAccount Status"
headAdminReuse = "Admins\tUsers\tNT"
headDomReuse = "User\tNT"
headLocal = "IP\tHostname\tAccount\tRID\tLM\tNT"
headWeak = "User\t\tUser"
headCrack = "RAW\tNT\tPlaintext"
splitReuse = "=============== Password Reuse ==============="
splitWeak = "============= Weak PW Management ============="
splitFiles = "================ Output Files ================"
splitGen = "==============================================\n"
splitForm = "=============== Excel Formulas ==============="
formReuseDom = '=COUNTIF(D$2:D$<RREUSE>, D2)'
formCrack = '=IFNA(IF(D2=VLOOKUP(D2,cracked!B:D,1,FALSE),"YES","-"),"-")'
formMethod = '=IFNA(VLOOKUP(D2,cracked!B:D,3,FALSE),"-")'
formPlain = '=IFNA(VLOOKUP(D2,cracked!B:D,2,FALSE),"-")'
formLength = '=IF(OR(H2="-",H2="N/A [BLANK]"),"-",LEN(H2))'
formBelowMinTemp = '=IF(ISNUMBER(I2),(IF(I2 < <RMINLEN>,"YES","-")),"-")'
formIsAdmin = '=IFERROR(IFNA(IF(RIGHT(A2,LEN(A2)-FIND("\\",A2)) = VLOOKUP((RIGHT(A2,LEN(A2)-FIND("\\",A2))),P:P,1,FALSE),"YES","-"),"-"),"-")'
formCrackPTemp = '="Cracked: " & TEXT(SUM(COUNTIF(F:F,"YES")/<RCRACKP>),"0.0%")'
formReuseLoc = '=COUNTIF(F$2:F$<RREUSE>, F2)'
formCrackLoc = '=IFNA(IF(F2=VLOOKUP(F2,cracked!B:D,1,FALSE),"YES","-"),"-")'
formMethodLoc = '=IFNA(VLOOKUP(F2,cracked!B:D,3,FALSE),"-")'
formPlainLoc = '=IFNA(VLOOKUP(F2,cracked!B:D,2,FALSE),"-")'
formSortIP = '=(VALUE(LEFT(A2,FIND(".",A2)-1))*10^9)+(VALUE(LEFT(RIGHT(A2,LEN(A2)-FIND(".",A2)),FIND(".",RIGHT(A2,LEN(A2)-FIND(".",A2)))-1))*10^6)+VALUE(LEFT(RIGHT(RIGHT(A2,LEN(A2)-FIND(".",A2)),LEN(RIGHT(A2,LEN(A2)-FIND(".",A2)))-FIND(".",RIGHT(A2,LEN(A2)-FIND(".",A2)))),FIND(".",RIGHT(RIGHT(A2,LEN(A2)-FIND(".",A2)),LEN(RIGHT(A2,LEN(A2)-FIND(".",A2)))-FIND(".",RIGHT(A2,LEN(A2)-FIND(".",A2)))))-1))*10^3+VALUE(RIGHT(RIGHT(RIGHT(A2,LEN(A2)-FIND(".",A2)),LEN(RIGHT(A2,LEN(A2)-FIND(".",A2)))-FIND(".",RIGHT(A2,LEN(A2)-FIND(".",A2)))),LEN(RIGHT(RIGHT(A2,LEN(A2)-FIND(".",A2)),LEN(RIGHT(A2,LEN(A2)-FIND(".",A2)))-FIND(".",RIGHT(A2,LEN(A2)-FIND(".",A2)))))-FIND(".",RIGHT(RIGHT(A2,LEN(A2)-FIND(".",A2)),LEN(RIGHT(A2,LEN(A2)-FIND(".",A2)))-FIND(".",RIGHT(A2,LEN(A2)-FIND(".",A2)))))))'

skipSprayUsers = ['krbtgt', 'guest']
statStrEnabled = "(status=Enabled)"
statStrDisabled = "(status=Disabled)"


# simple class to make referencing users easier as opposed to ordered list or dictionary
class winUser:
    def __init__(self, username, rid, lmhash, nthash, isadmin=False, ipaddr=None, plaintext=None, weak=False, status=None):
        self.username                       = username
        self.rid                            = rid
        self.lmhash                         = lmhash
        self.nthash                         = nthash
        self.isadmin                        = isadmin
        self.ipaddr                         = ipaddr
        self.plaintext                      = plaintext
        self.weak                           = weak
        self.status                         = status

def parseArgs():
    ap = argparse.ArgumentParser(description='Secretsdump Report Generator', formatter_class=lambda prog: argparse.HelpFormatter(prog,max_help_position=50))
    apInput = ap.add_mutually_exclusive_group(required=True)
    apFilter = ap.add_mutually_exclusive_group()
    apInput.add_argument('-i', '--ntds', dest='inFile', metavar='inputFile', action='store', help='[X] input NTDS/SAM file')
    apInput.add_argument('-d', '--dir', dest='inDir', metavar='inputDir', action='store', help='[X] directory of SAM files to parse. files must be named like <IP>.sam')
    ap.add_argument('-o', '--outfile', dest='outFile', metavar='outputFile', action='store', help='prepend output file name')
    ap.add_argument('-l', '--users', dest='adminFile', metavar='adminsFile', action='store', help='text file of privileged users')
    ap.add_argument('-p', '--potfile', dest='potFile', metavar='hc.txt', action='store', help='hashcat/john potfile containing <hash>:<plaintext>')
    ap.add_argument('-user', dest='parseUser', action='store_true', default=False, help='parse all domain reuse')
    ap.add_argument('-admin', dest='parseAdmin', action='store_true', default=False, help='parse admin reuse')
    ap.add_argument('-spray', dest='oSpray', action='store_true', default=False, help='create "<user> <lm:nt>" file for PtH spraying')
    ap.add_argument('-status', dest='parseStat', action='store_true', default=False, help='include account status from "secretsdump.py -user-status" in parsed TSV (ntds only)')
    apFilter.add_argument('-enabled', dest='pEnable', action='store_true', default=False, help='[X] filter reporting files to only enabled accounts. Does not affect uniqhashes')
    apFilter.add_argument('-history', dest='parseHistory', action='store_true', default=False, help='[X] include NTDS password history in parsed NTDS tsv. Does not affect uniqhashes')
    ap.add_argument('-computer', dest='pComp', action='store_true', default=False, help='include computer hashes in uniqhashes')
    ap.add_argument('-x', '--excel', dest='genExcel', action='store_true', default=False, help='generate excel formulas for tracking document')
    ap.add_argument('-pass-len', dest='xpassLen', default=8, metavar='MinPassLen', action='store', help='AD Minimum Password Length Policy setting. Only used for excel formulas')

    args = ap.parse_args()

    if not (args.inFile or args.inDir):
        print("You must specify either -i <inFile> or -d <inDir>")
        exit(1)
    elif args.inFile:
        cParse = "file"
    elif args.inDir:
        cParse = "dir"

    if ((args.parseAdmin) and not (args.adminFile)):
        print("-admin requires -l <adminFile>")
        exit(1)

    if args.potFile:
        hParse = True
    else:
        hParse = False

    return args.inFile, args.outFile, args.inDir, args.adminFile, args.parseAdmin, args.parseUser, args.parseHistory, args.potFile, cParse, hParse, args.genExcel, args.xpassLen, args.oSpray, args.parseStat, args.pEnable, args.pComp

def samError(inDir):
    print(f"No files found in {inDir} that match the proper convention")
    print("SAM files must be named with one of the following conventions:")
    print("<IP>_[whatever].sam")
    print("<IP>-[whatever].sam")
    print("<IP>.sam")
    exit(1)

def parseDir(inDir):
    samFiles = []
    wUsers = []
    allNT = []
    uniqNT = []

    tmpFiles = glob(f"{inDir}/*.sam")
    if len(tmpFiles) == 0:
        samError(inDir)

    for tmpFile in tmpFiles:
        fileName = os.path.basename(tmpFile)
        if '_' in fileName:
            fileIP = fileName.split('_')[0]
        elif '-' in fileName:
            fileIP = fileName.split('-')[0]
        # support <IP>.sam
        else:
            fileIP = fileName.split('.sam')[0]
        try:
            if ip_address(fileIP):
                samFiles.append(tmpFile)
        except:
            pass
    if len(samFiles) == 0:
        samError(inDir)

    for samFile in samFiles:
        if '_' in samFile:
            samIP = os.path.basename(samFile).split('_')[0]
        elif '-' in samFile:
            samIP = os.path.basename(samFile).split('-')[0]
        # support <IP>.sam
        else:
            samIP = os.path.basename(samFile).split('.sam')[0]
        with open(samFile, 'r') as sam:
            samLines = sam.readlines()
        for line in samLines:
            sUser, sRID, sLM, sNT = line.split(":", 4)[0:4]
            allNT.append(sNT)
            samUser = winUser(sUser, sRID, sLM, sNT, ipaddr=samIP)
            wUsers.append(samUser)
    uniqNT = pd.Series(allNT).drop_duplicates().tolist() # pandas makes this op pretty simple
    numSam = len(samFiles)

    #for u in wUsers:
        #print("{}\t{}\t{}\t{}\t{}".format(u.ipaddr, u.username, u.rid, u.nthash, u.isadmin))
    return wUsers, uniqNT, allNT, numSam

def parseFile(inFile, outFile, adminFile, parseHistory=False, pEnable=False, pComp=False):
    allNT = []
    wUsers = []
    # set adminFile to empty list if not specified from commandline
    if adminFile is not None:
        with open(adminFile, "r") as adminf:
            admins = adminf.readlines()
        for i in range(len(admins)):
            admins[i] = admins[i].strip()
    else:
        admins = []
    # read in the NTDS file to a list
    with open(inFile, "r") as ntds:
        ntdsLines = ntds.readlines()
    # parse each line from the NTDS into a winUser object. split the secretsdump on ':' into 5 fields, select the first 4 fields.
    for line in ntdsLines:
        # breaks on blank lines. should be a try/except but im lazy
        if len(line) <= 1:
            continue
        nUser, nRID, nLM, nNT = line.split(":", 4)[0:4]
        # skip companyName for instances where the tester added a new account
        if ((not len(companyName) == 0) and companyName in nUser):
            continue
        # if nUser represents a computer account, and -computer is NOT specified, drop the account
        if (("$" in nUser) and not (pComp)):
            continue
        # add the NT hash to allNT, including computer accounts if -computer
        allNT.append(nNT)
        # if -computer is specified, the nUser remains. for these cases, now drop the account
        if "$" in nUser:
            continue
        # skip history unless specified with -history
        if (("_history" in nUser) and not (parseHistory)):
            continue

        # try/except is needed to not break on accounts like krbtgt that dont have a DOMAIN in the username field. added benefit of matching either samaccountname or DOM\User format for adminFile
        # map casefold is a nifty trick for case insensitive matching without any re nonsense
        try:
            if nUser.split('\\')[1].casefold() in map(str.casefold, admins):
                nAdmin = True
            else:
                nAdmin = False
        except:
            if nUser.casefold() in map(str.casefold, admins):
                nAdmin = True
            else:
                nAdmin = False
        '''
        ntdsDict[nUser] = {
                "RID": nRID,
                "LM": nLM,
                "NT": nNT,
                "ADMIN": nAdmin
                }
        '''
        wUser = winUser(nUser, nRID, nLM, nNT, nAdmin)
        if statStrEnabled in line:
            wUser.status = "Enabled"
        elif statStrDisabled in line:
            wUser.status = "Disabled"
        wUsers.append(wUser)

    uniqNT = pd.Series(allNT).drop_duplicates().tolist() # pandas makes this op pretty simple

    # handle -enabled
    if pEnable:
        #for wu in [user for user in wUsers if user.status != 'Enabled']:
        #    wUsers.remove(wu)
        wUsers = [u for u in wUsers if u.status == 'Enabled']
        if len(wUsers) == 0:
            print("-enabled specified but there aren't any enabled users or user status is missing from ntds!")

    del ntdsLines
    return wUsers, uniqNT, allNT

def parseAdminReuse(wUsers):
    adminHashes = []
    adminReuse = {}
    numAdminReuse = 0
    numAdminReuseUsers = 0
    adminUsers = [user for user in wUsers if user.isadmin == True]
    for admin in adminUsers:
        adminHashes.append(admin.nthash)
    # we're making comparisons based on just the unique admin hashes
    adminHashes = pd.Series(adminHashes).drop_duplicates().tolist()
    for aHash in adminHashes:
        # skip null NT 
        if aHash == nullNT:
            continue
        rAdmins = [admin.username for admin in adminUsers if admin.nthash == aHash]
        rUsers = [user.username for user in wUsers if ((user.nthash == aHash) and (user.isadmin == False))]
        #print("num admins: ", len(rAdmins))
        #print("num users: ", len(rUsers))
        # if the admins hash isn't reused, discard it
        if ((len(rAdmins) == 1) and (len(rUsers) == 0)):
            continue
        # Replace empty Users field with "N/A"
        if len(rUsers) == 0:
            rUsers.append("N/A")
        adminReuse[aHash] = {'Admins': ';;; '.join(rAdmins), 'Users': ';;; '.join(rUsers)}
        numAdminReuse += len(rAdmins)
        numAdminReuseUsers += len(rUsers)
    return adminReuse, numAdminReuse, numAdminReuseUsers

def parseAllReuse(wUsers, allNT, uniqNT):
    c = Counter(allNT)
    domReuse = []
    sharedUniq = []
    numDomReuse = 0
    for uHash in uniqNT:
        # skip null NT and passwords not reused
        if ((uHash == nullNT) or (c[uHash] == 1)):
            continue
        hReuse = {}
        rUsers = [user.username for user in wUsers if user.nthash == uHash]
        # quick fix for previously reused password (ie nthash from _history) being here.
        if not (len(rUsers) >= 2):
            continue
        hReuse = {'Hash': uHash, 'Users': rUsers}
        # move sharedUniq
        sharedUniq.append(uHash)
        domReuse.append(hReuse)
        numDomReuse += len(rUsers)
    domReuse.sort(key=lambda x: len(x.get('Users')), reverse=True)
    numDomPw = len(sharedUniq)
    del sharedUniq
    return domReuse, numDomReuse, numDomPw

def writeOutput(outFile, wUsers, uniqNT, allNT, cParse, hParse, crackedPW, parseAdmin=False, parseUser=False, oSpray=False, parseStat=False, pEnable=False, numWeakUsers=0):
    outUniq = outFile + extUniq
    outTsv = outFile + extTsv
    outAdminReuse = f"{outFile}-pw-reuse-admin{extTsv}"
    outDomReuse = f"{outFile}-pw-reuse-all{extTsv}"
    outAdminWeak = f"{outFile}-weak-pw-admin{extTsv}"
    outDomWeak = f"{outFile}-weak-pw-all{extTsv}"
    outCracked = f"{outFile}-cracked{extTsv}"
    outSpray = f"{outFile}-spray.txt"
    outputFiles = {}
    numDomReuse = None
    numDomPw = None
    numAdminReuse = None
    numAdminReuseUsers = None

    # writing uniqNT *shouldn't* need to be under a cParse
    with open(outUniq, 'w') as funiq:
        funiq.write('\n'.join(uniqNT))
    outputFiles['uniq'] = outUniq

    # if wUsers is empty (due to -enabled on an ntds with no user status), skip reporting files and move to the console output from report()
    if len(wUsers) == 0:
        print("No valid users found. Skipping report files")
        return outputFiles, numDomReuse, numDomPw, numAdminReuse, numAdminReuseUsers

    # filtering enabled users *shouldnt* cause conflicts with reporting files, even if individual lists may be empty
    if cParse == "file":
        # if -status specified AND at least one user has status: proceed with ntdsstat. otherwise, ignore -status and use ntds
        # also, choose tsv header
        if ((parseStat) and (len([user for user in wUsers if user.status != None]) > 0)):
            tableLines = formatOutput(wUsers, fType="ntdsstat")
            cHeadNTDS = headNTDSStatus
        else:
            tableLines = formatOutput(wUsers, fType="ntds")
            cHeadNTDS = headNTDS
        with open(outTsv, 'w') as ftsv:
            ftsv.write("{}\n".format(cHeadNTDS))
            for tl in tableLines:
                ftsv.write("{}\n".format(tl))
        outputFiles['tsv'] = outTsv

        # -history caused an issue with pw reuse. to fix, remove all users with _history
        # put here because we want histories written to report tsv if -history
        wUsers = [u for u in wUsers if not '_history' in u.username]

        if parseAdmin:
            adminReuse, numAdminReuse, numAdminReuseUsers = parseAdminReuse(wUsers)
            tableLines = formatOutput(adminReuse, fType="reuseadmin")
            with open(outAdminReuse, 'w') as far:
                far.write("{}\n".format(headAdminReuse))
                for tl in tableLines:
                    far.write("{}\n".format(tl))
                #for aHash in adminReuse.keys():
                    #print("{}\t{}\t{}".format(adminReuse[aHash]['Admins'], adminReuse[aHash]['Users'], aHash))
                    #f3.write("{}\t{}\t{}\n".format(adminReuse[aHash]['Admins'], adminReuse[aHash]['Users'], aHash))
            outputFiles['admin'] = outAdminReuse

        if parseUser:
            domReuse, numDomReuse, numDomPw = parseAllReuse(wUsers, allNT, uniqNT)
            tableLines = formatOutput(domReuse, fType="reuseuser")
            #print(';;; '.join(domReuse[0]['Users']))
            with open(outDomReuse, 'w') as fur:
                fur.write("{}\n".format(headDomReuse))
                for tl in tableLines:
                    fur.write("{}\n".format(tl))
                #for uHash in domReuse:
                    #for u in uHash['Users']:
                        #print("{}\t{}".format(u, uHash['Hash']))
                        #f4.write("{}\t{}\n".format(u, uHash['Hash']))
            outputFiles['user'] = outDomReuse

    elif cParse == "dir":
        tableLines = formatOutput(wUsers, fType="local")
        with open(outTsv, 'w') as fl:
            fl.write("{}\n".format(headLocal))
            for tl in tableLines:
                fl.write("{}\n".format(tl))
            #for u in wUsers:
                #f1.write("{}\t<Host>\t{}\t{}\t{}\t{}\n".format(u.ipaddr, u.username, u.rid, u.lmhash, u.nthash))
        outputFiles['tsv'] = outTsv
        # if moving uniqNT to out of cParse breaks local, move it back

    if oSpray:
        tableLines = formatOutput(wUsers, fType="spray")
        with open(outSpray, 'w') as fspray:
            for tl in tableLines:
                fspray.write("{}\n".format(tl))
        outputFiles['spray'] = outSpray

    if numWeakUsers > 0:
        tableLines = formatOutput(crackedPW, fType="crackedpw")
        with open(outCracked, 'w') as cf:
            cf.write("{}\n".format(headCrack))
            for tl in tableLines:
                cf.write("{}\n".format(tl))
        outputFiles['crackedpw'] = outCracked

        weakUsers = [user.username for user in wUsers if user.weak == True]
        tableLines = formatOutput(weakUsers, fType="weakuser")
        with open(outDomWeak, 'w') as wuf:
            wuf.write("{}\n".format(headWeak))
            for tl in tableLines:
                wuf.write("{}\n".format(tl))
        outputFiles['weakdom'] = outDomWeak

        if parseAdmin:
            weakAdmins = [user.username for user in wUsers if ((user.weak == True) and (user.isadmin == True))]
            tableLines = formatOutput(weakAdmins, fType="weakuser")
            with open(outAdminWeak, 'w') as waf:
                waf.write("{}\n".format(headWeak))
                for tl in tableLines:
                    waf.write("{}\n".format(tl))
            outputFiles['weakadmin'] = outAdminWeak

    return outputFiles, numDomReuse, numDomPw, numAdminReuse, numAdminReuseUsers

def formatOutput(data, fType):
    newTableLines = []
    if fType == "weakuser":
        # goofy ass math to properly align the columns
        if ((len(data) % 2) == 0):
            nC1 = len(data)//2
        else:
            nC1 = len(data)//2 + 1
        C1 = data[:nC1]
        C2 = data[nC1:]
        if not len(C1) == len(C2):
            C2.append('N/A')
        for i in range(len(C1)):
            newTableLines.append("{}\t\t{}".format(C1[i], C2[i]))

    elif fType == "ntds":
        for u in data:
            newTableLines.append("{}\t{}\t{}\t{}".format(u.username, u.rid, u.lmhash, u.nthash))

    elif fType == "ntdsstat":
        for u in data:
            newTableLines.append("{}\t{}\t{}\t{}\t\t\t\t\t\t\t\t{}".format(u.username, u.rid, u.lmhash, u.nthash, u.status))
    
    elif fType == "spray":
        # skip computers, blank NT, known accounts
        for u in data:
            if ((u.nthash == nullNT) or ("$" in u.username)):
                continue
            if "\\" in u.username:
                tUser = u.username.split("\\")[1]
            else:
                tUser = u.username
            if tUser.lower() in skipSprayUsers:
                continue
            newTableLines.append("{} {}:{}".format(tUser, u.lmhash, u.nthash))

    elif fType == "local":
        for u in data:
            newTableLines.append("{}\t<Host>\t{}\t{}\t{}\t{}".format(u.ipaddr, u.username, u.rid, u.lmhash, u.nthash))

    elif fType == "reuseuser":
        for uHash in data:
            for u in uHash['Users']:
                newTableLines.append("{}\t{}".format(u, uHash['Hash']))

    elif fType == "reuseadmin":
        for aHash in data.keys():
            newTableLines.append("{}\t{}\t{}".format(data[aHash]['Admins'], data[aHash]['Users'], aHash))

    elif fType == "crackedpw":
        for cp in data.keys():
            rp = "{}:{}".format(cp, data[cp])
            newTableLines.append("{}\t{}\t{}".format(rp, cp, data[cp]))

    return newTableLines

def report(outputFiles, uniqNT, wUsers, cParse, numDomReuse, numDomPw, numAdminReuse, numAdminReuseUsers, numSam, numWeakUsers, numWeakAdmins, hParse, genExcel, xpassLen, pEnable, inFile=None, inDir=None):
    fmsg = f"{splitFiles}\n"
    statsWeak = f"{splitWeak}\n"
    statsReuse = f"{splitReuse}\n"

    # restructure
    # we dont really care about -enabled with cParse dir, but the option would still be valid if specified. because of this, put pEnable text under cParse file
    if cParse == "file":
        fmsg += "Parsed Input File:\t\t\t{}\n".format(inFile)
        if pEnable:
            fmsg += "Reporting files filtered to enabled users\n"
    elif cParse == "dir":
        fmsg += "Parsed {} SAM files in {}\n".format(numSam, inDir)

    # drop unique verbiage for cParse output file, only add output file if actually written
    if 'tsv' in outputFiles.keys():
        fmsg += "Output Report TSV:\t\t\t{}\n".format(outputFiles['tsv'])
    # uniq hashes *shouldnt* need to be in a cParse. it *should* also always be present if we made it this far, but w/e
    if 'uniq' in outputFiles.keys():
        fmsg += "Output Uniq hashes:\t\t\t{}\n".format(outputFiles['uniq'])
    if 'spray' in outputFiles.keys():
        fmsg += "Output PtH spray file:\t\t\t{}\n".format(outputFiles['spray'])
    # admin and user reuse are only relevant for cParse file, they wont be present from cParse dir; meaning they dont need to actually be in a cParse
    if 'admin' in outputFiles.keys():
        statsReuse += f"Admin accounts reusing passwords:\t\t{numAdminReuse}\n"
        statsReuse += f"User accounts sharing passwords with admins:\t{numAdminReuseUsers}\n"
        fmsg += "Output Admin reuse TSV:\t\t\t{}\n".format(outputFiles['admin'])
    if 'user' in outputFiles.keys():
        statsReuse += f"User accounts reusing passwords:\t\t{numDomReuse}\n"
        statsReuse += f"Number of unique shared passwords:\t\t{numDomPw}\n"
        fmsg += "Output Domain reuse TSV:\t\t{}\n".format(outputFiles['user'])

    # leaving these in here for now in case i broke something. to be removed at a later date
    #if cParse == "file":
        #fmsg += "Parsed input file:\t\t\t{}\n".format(inFile)
        #fmsg += "Output report TSV:\t\t\t{}\n".format(outputFiles['tsv'])
        #fmsg += "Output uniq hashes:\t\t\t{}\n".format(outputFiles['uniq'])
        #if 'admin' in outputFiles.keys():
        #    statsReuse += f"Admin accounts reusing passwords:\t\t{numAdminReuse}\n"
        #    statsReuse += f"User accounts sharing passwords with admins:\t{numAdminReuseUsers}\n"
        #    fmsg += "Output admin reuse TSV:\t\t\t{}\n".format(outputFiles['admin'])
        #if 'user' in outputFiles.keys():
        #    statsReuse += f"User accounts reusing passwords:\t\t{numDomReuse}\n"
        #    statsReuse += f"Number of unique shared passwords:\t\t{numDomPw}\n"
        #    fmsg += "Output dom reuse TSV:\t\t\t{}\n".format(outputFiles['user'])

    #elif cParse == "dir":
        #fmsg += "Parsed {} SAM files in {}\n".format(numSam, inDir)
        #fmsg += "Output Local PW Reuse TSV:\t\t{}\n".format(outputFiles['tsv'])
        #fmsg += "Output uniq hashes file:\t\t{}\n".format(outputFiles['uniq'])

    # maybe no enabled or current user passwords cracked. add a condition for this
    # additionally, restructure this to look for the output files instead of simply hParse (set True with -p <potFile>)
    # writeOutput from hParse to check numWeakUsers. if no weak users, the file isnt written and added to outputFiles
    if 'weakdom' in outputFiles.keys():
        numUsers = len(wUsers)
        numUsers = len([u for u in wUsers if not '_history' in u.username])
        pWeakPW = str(f"{numWeakUsers/numUsers:.0%}")
        statsWeak += f"Percentage accounts w/ Weak Passwords:\t\t{pWeakPW}\n"
        statsWeak += f"Number of accounts with weak passwords:\t\t{numWeakUsers}\n"
        fmsg += "Output Weak Domain Password TSV:\t{}\n".format(outputFiles['weakdom'])

    # -user and -admin ONLY runs pw reuse for all domain user and administrative accounts respectively, and have no bearing on running through cracked passwords
    # -p <potFile> implicitly checks the potFile against ALL domain user accounts. However:
    # admin status requires -l <adminsFile>. when -p and -l are combined, only then can weakadmin occur. while you typically can't have weakadmin without weakdom, weakadmin is not necessarily dependent on weakdom.
    # for this reason, move weakadmin out from under weakdom
    if 'weakadmin' in outputFiles.keys():
        statsWeak += f"Number of admins with weak passwords:\t\t{numWeakAdmins}\n"
        fmsg += "Output Weak Admin Password TSV:\t\t{}\n".format(outputFiles['weakadmin'])
    if 'crackedpw' in outputFiles.keys():
        fmsg += "Output Cracked Passwords TSV:\t\t{}\n".format(outputFiles['crackedpw'])

    # leaving these in here for now in case i broke something. to be removed at a later date
    #if hParse:
    #    numUsers = len(wUsers)
    #    pWeakPW = str(f"{numWeakUsers/numUsers:.0%}")
    #    statsWeak += f"Percentage accounts w/ Weak Passwords:\t\t{pWeakPW}\n"
    #    statsWeak += f"Number of accounts with weak passwords:\t\t{numWeakUsers}\n"
    #    fmsg += "Output Weak Domain Password TSV:\t{}\n".format(outputFiles['weakdom'])
    #    fmsg += "Output Cracked Passwords TSV:\t\t{}\n".format(outputFiles['crackedpw'])
    #    if 'weakadmin' in outputFiles.keys():
    #        statsWeak += f"Number of admins with weak passwords:\t\t{numWeakAdmins}\n"
    #        fmsg += "Output Weak Admin Password TSV:\t\t{}\n".format(outputFiles['weakadmin'])

    print(fmsg.strip())
    print(splitGen)
    # fix always printing statsReuse when not specified
    if (('admin' in outputFiles.keys()) or ('user' in outputFiles.keys())):
        print(statsReuse.strip())
        print(splitGen)
    if numWeakUsers > 0:
        print(statsWeak.strip())
        print(splitGen)
    if genExcel:
        rFormula = generateFormulas(wUsers, cParse, xpassLen)
        print(splitForm)
        print(rFormula)
        print(splitGen.strip())

def parseHashcat(wUsers, potFile):
    crackedPW = {}
    numWeakUsers = 0
    numWeakAdmins = 0
    numBlank = 0
    with open(potFile, 'r') as pf:
        potLines = pf.readlines()
    for i in range(len(potLines)):
        potLines[i] = potLines[i].strip('\n')
        pHash = potLines[i].split(':')[0]
        if pHash == nullNT:
            pPlaintext = nullNTpt
        else:
            #pPlaintext = potLines[i].split(':')[1]
            # below str.partition() is chosen over str.split() in case plaintext contains ':'
            pPlaintext = potLines[i].partition(':')[2]
        crackedPW[pHash] = pPlaintext
        for u in wUsers:
            if '_history' in u.username:
                continue
            if u.nthash == pHash:
                u.plaintext = pPlaintext
                if u.nthash == nullNT:
                    numBlank += 1
                else:
                    u.weak = True
                    numWeakUsers += 1
                    if u.isadmin == True:
                        numWeakAdmins += 1
    #for cp in crackedPW.keys():
        #print("{}\t{}".format(cp, crackedPW[cp]))
    return wUsers, numWeakUsers, numWeakAdmins, numBlank, crackedPW

def generateFormulas(wUsers, cParse, xpassLen=8):
    numAcc = len(wUsers)
    numAccLines = numAcc + 1
    if cParse == "file":
        formReuse = formReuseDom.replace('<RREUSE>', str(numAccLines))
        formCrackP = formCrackPTemp.replace('<RCRACKP>', str(numAcc))
        formBelowMin = formBelowMinTemp.replace('<RMINLEN>', str(xpassLen))
        colformReuse = "E2"
        colformCrack = "F2"
        colformMethod = "G2"
        colformPlain = "H2"
        colformLength = "I2"
        colformBelowMin = "J2"
        colformIsAdmin = "K2"
        colformCrackP = "M1"
        rFormula = ""
        rFormula += "{}:\t\t{}\n".format(colformReuse, formReuse)
        rFormula += "{}:\t\t{}\n".format(colformCrack, formCrack)
        rFormula += "{}:\t\t{}\n".format(colformMethod, formMethod)
        rFormula += "{}:\t\t{}\n".format(colformPlain, formPlain)
        rFormula += "{}:\t\t{}\n".format(colformLength, formLength)
        rFormula += "{}:\t\t{}\n".format(colformBelowMin, formBelowMin)
        rFormula += "{}:\t\t{}\n".format(colformIsAdmin, formIsAdmin)
        rFormula += "{}:\t\t{}".format(colformCrackP, formCrackP)
        #rFormula += "{}:\t\t{}".format()
    elif cParse == "dir":
        # fix column references, add sort ip formula
        formReuse = formReuseLoc.replace('<RREUSE>', str(numAccLines))
        colformReuse = "G"
        colformCrack = "H"
        colformMethod = "I"
        colformPlain = "J"
        colformSort = "K"
        rFormula = ""
        rFormula += "{}:\t\t{}\n".format(colformReuse, formReuse)
        rFormula += "{}:\t\t{}\n".format(colformCrack, formCrackLoc)
        rFormula += "{}:\t\t{}\n".format(colformMethod, formMethodLoc)
        rFormula += "{}:\t\t{}\n".format(colformPlain, formPlainLoc)
        rFormula += "{}:\t\t{}\n".format(colformSort, formSortIP)

    return rFormula

def main():
    inFile, outFile, inDir, adminFile, parseAdmin, parseUser, parseHistory, potFile, cParse, hParse, genExcel, xpassLen, oSpray, parseStat, pEnable, pComp = parseArgs()
    # debug
    '''
    print(f"inFile {inFile}")
    print(f"outFile {outFile}")
    print(f"inDir {inDir}")
    print(f"adminFile {adminFile}")
    print(f"parseAdmin {parseAdmin}")
    print(f"parseUser {parseUser}")
    print(f"parseHistory {parseHistory}")
    print(f"potFile {potFile}")
    print(f"cParse {cParse}")
    print(f"hParse {hParse}")
    print(f"genExcel {genExcel}")
    print(f"xpassLen {xpassLen}")
    print(f"oSpray {oSpray}")
    print(f"parseStat {parseStat}")
    print(f"pEnable {pEnable}")
    '''

    if cParse == "file":
        if outFile is None:
            outFile = defaultOutFile
        wUsers, uniqNT, allNT = parseFile(inFile, outFile, adminFile, parseHistory, pEnable, pComp)
        numSam = None
    elif cParse == "dir":
        if outFile is None:
            outFile = f"local-{defaultOutFile}"
        wUsers, uniqNT, allNT, numSam = parseDir(inDir)

    if hParse:
        wUsers, numWeakUsers, numWeakAdmins, numBlank, crackedPW = parseHashcat(wUsers, potFile)
    else:
        numWeakUsers = 0
        numWeakAdmins = 0
        numBlank = 0
        crackedPW = None

    outputFiles, numDomReuse, numDomPw, numAdminReuse, numAdminReuseUsers = writeOutput(outFile, wUsers, uniqNT, allNT, cParse, hParse, crackedPW, parseAdmin, parseUser, oSpray, parseStat, pEnable, numWeakUsers)
    report(outputFiles, uniqNT, wUsers, cParse, numDomReuse, numDomPw, numAdminReuse, numAdminReuseUsers, numSam, numWeakUsers, numWeakAdmins, hParse, genExcel, xpassLen, pEnable, inFile, inDir)


if __name__ == "__main__":
    main()



