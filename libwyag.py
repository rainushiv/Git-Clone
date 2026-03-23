import argparse
import configparser
from datetime import datetime
import grp,pwd
from fnmatch import fnmatch
import hashlib
from math import ceil
import os
import re
import sys
import zlib

argparser = argparse.ArgumentParser(description="Content Tracker")
argsubparser =argparser.add_subparsers(title="Commands", dest="command")
argsubparser.required = True

def main(argv = sys.argv[1:]):
    args = argparser.parse_args(argv)
    match args.command:
        case "add":             cmd_add(args)
        case "cat-file":        cmd_cat_file(args)
        case "check-ignore":    cmd_check_ignore(args)
        case "checkout":        cmd_checkout(args)
        case "commit":          cmd_commit(args)
        case "hash-object":     cmd_hash_object(args)
        case "init":            cmd_init(args)
        case "log":             cmd_log(args)
        case "ls-files":        cmd_ls_files(args)
        case "ls-tree":         cmd_ls_tree(args)
        case "rev-parse":       cmd_rev_parse(args)
        case "rm":              cmd_rm(args)
        case "show-ref":        cmd_show_ref(args)
        case "status":          cmd_status(args)
        case "tag":             cmd_tag(args)
        case _:                 print("Bad command.")


class GitRespository(object):
    """The git Respository Object"""
    worktree = None
    gitdir = None
    conf = None

    def __init__(self,path, force = False):
        self.worktree = path
        self.gitdir = os.path.join(path, ".git")
        if not (force or os.path.isdir(self.gitdir)):
            raise Exception(f"Not a Git Repository {path}")
        # Ingests config files found
        self.conf = configparser.ConfigParser()
        cf = repo_file(self,"config")
        if cf and os.path.exists(cf):
            self.conf.read([cf])
        elif not force: 
            raise Exception("Configuration file missing")

        if not force:
            vers = int(self.conf.get("core","respoitoryformatversion"))
            if vers != 0:
                raise Exception(f"Unsupported repositoryformatversion: {vers}")
            
def repo_path(repo, *path):
    """Compute path under repo's gitdir"""
    return os.path.join(repo.gitdir, *path)

def repo_file(repo,*path, mkdir = False):
    """Same as repo path, but create dirname if absent"""
    if repo_dir(repo, *path[:-1], mkdir=mkdir):
        return repo_path(repo, *path)
    
def repo_dir(repo, *path, mkdir = False):

    path = repo_path(repo, *path)
    if os.path.exists(path):
        if (os.path.isdir(path)):
            return path
        else:
            raise Exception(f"Not a directory {path}")
        
    
    if mkdir:
        os.makedirs(path)
        return path
    else:
        return None
    
def repo_create(path):
    """Creates New Respository at the path"""
    repo = GitRespository(path, True)

    #Make sure the path doesn't exist or is an 
    #empty dir

    if os.path.exists(repo.worktree):
        if not os.path.isdir(repo.worktree):
            raise Exception(f"{path} is not a directory!")
        
        if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir):
            raise Exception(f"{path} is not empty!")
    
    else:
        os.makedirs(repo.worktree)

    assert repo_dir(repo,"branches", mkdir = True)
    assert repo_dir(repo,"objects", mkdir = True)
    assert repo_dir(repo,"refs","tags", mkdir = True)
    assert repo_dir(repo,"refs","heads", mkdir = True)

    with open(repo_file(repo,"description"), "w") as f: 
        f.write("Unamed respository; edit this file 'description' to name the respository.\n")

    with open(repo_file(repo,"HEAD"),"w") as f:
        f.write("ref: refs/heads/master\n")

    with open(repo_file(repo,"config"),"w") as f:
        config = repo_default_config()
        config.write(f)

    return repo 

def repo_default_config():
    ret = configparser.ConfigParser()
    ret.add_section("core")
    ret.set("core","repositoryformatversion","0")
    ret.set("core","filemode","false")
    ret.set("core","bare","false")
    return ret


argsp = argsubparser.add_parser("init", help="Initializa a new, empty repository.")

argsp.add_argument("path", metavar="directory", nargs="?",default=".",help="Where to create the repository")

def cmd_init(args):
    repo_create(args.path)

def repo_find(path=".", required=True):
    path = os.path.realpath(path)

    if os.path.isdir(os.path.join(path,".git")):
        return GitRespository(path)
    parent = os.path.realpath(os.path.join(path,".."))

    if parent == path:
        if required:
            raise Exception("No git directory.")
        else:
            return None
        
    return repo_find(parent,required)

class GitObject(object):
    def __init__(self, data = None):
        if data != None:
            self.deserialization(data)
        else:
            self.init()

    def serialize(self,repo):
        """Will be implemented by subclasses"""
        raise Exception("Unimplemented")
    def deserialize(self,data):
        raise Exception("Unimplemented")
    
    def init(self):
        pass

def object_read(repo,sha):
    path = repo_file(repo,"objects")

    if not  os.path.isfile(path):
        return None 
    
    with open(path,"rb") as f: 
        raw = zlib.decompress(f.read())
        x = raw.find(b' ')
        fmt = raw[0:x]
        y = raw.find(b'\x00',x)
        size = int(raw[x:y].decode("ascii"))
        if size != len(raw)-y-1:
            raise Exception(f"Malformed object {sha}: bad length")
        
        match fmt:
            case b'commit'  : c=GitCommit 
            case b'tree'    : c=GitTree 
            case b'tag'     : c=GitTag 
            case b'blob'    : c=GitBlob
            case _:
                raise Exception(f"Unknown type {fmt.decode('ascii')} for object {sha}") 
            
        return c(raw[y + 1: ])
    

def object_write(obj, repo=None):
    data = obj.serialize()
    
    result = obj.fmt+b' '+ str(len(data)).encode() + b'\x00' + data 

    sha = hashlib.sha1(result).hexdigest()

    if repo:

        path = repo_file(repo,"objects",sha[0:2],sha[2:],mkdir = True)

        if not os.path.exists(path):
            with open(path,'wb') as f: 
                f.write(zlib.compress(result))

    return sha

class GitBlob(GitObject):
    fmt = b'blob'