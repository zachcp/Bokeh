
import protocol
import requests
import urlparse
import utils
import uuid
import logging
import cPickle as pickle
import redis

import numpy as np
log = logging.getLogger(__name__)

class ContinuumModel(object):
    collections = ['Continuum', 'Collections']    
    def __init__(self, typename, **kwargs):
        self.attributes = kwargs
        self.typename = typename
        self.attributes.setdefault('id', str(uuid.uuid4()))
        self.id = self.get('id')
        
    def ref(self):
        return {
            'collections' : self.collections,
            'type' : self.typename,
            'id' : self.attributes['id']
            }
    def get(self, key, default=None):
        return self.attributes.get(key, default)
    
    def get_ref(self, field, client):
        ref = self.get(field)
        return client.get(ref['type'], ref['id'])
    
    def vget_ref(self, field, client):
        return [client.get(ref['type'], ref['id']) for ref in \
                self.attributes.get(field)]
    
    def set(self, key, val):
        self.attributes[key] = val
        
    def unset(self, key):
        del self.attributes[key]
           
    def to_broadcast_json(self):
        #more verbose json, which includes collection/type info necessary
        #for recon on the JS side.
        json = self.ref()
        json['attributes'] = self.attributes
        return json
    
    def to_json(self):
        return self.attributes

    def __str__(self):
        return "Model:%s" % self.typename
    
    def __repr__(self):
        return self.__str__()
    
        
class ContinuumModelsClient(object):
    def __init__(self, docid, baseurl, apikey, ph):
        self.apikey = apikey
        self.ph = ph
        self.baseurl = baseurl
        parsed = urlparse.urlsplit(baseurl)
        self.docid = docid
        session = requests.session()
        session.headers.update({'content-type':'application/json'})
        session.cookies.update({'bokeh-api-key' : self.apikey})
        session.verify = False
        self.s = session 
        super(ContinuumModelsClient, self).__init__()
        self.buffer = []
        
    def delete(self, typename, id):
        url = utils.urljoin(self.baseurl, self.docid +"/", typename + "/", id)
        self.s.delete(url)
        
    def buffer_sync(self):
        data = self.ph.serialize_web([x.to_broadcast_json() \
                                      for x in self.buffer])
        url = utils.urljoin(self.baseurl, self.docid + "/", 'bulkupsert')
        self.s.post(url, data=data)
        self.buffer = []
        
    def create(self, model, defer=False):
        if not model.get('docs'):
            model.set('docs', [self.docid])
        if defer:
            self.buffer.append(model)
        else:
            url = utils.urljoin(self.baseurl,
                                self.docid + "/",
                                model.typename)
            log.debug("create %s", url)
            self.s.post(url, data=self.ph.serialize_msg(model.to_json()))
        return model

    def update(self, model, defer=False):
        if not model.get('docs'):
            model.set('docs', [self.docid])
        if defer:
            self.buffer.append(model)
        else:
            url = utils.urljoin(self.baseurl,
                                self.docid + "/",
                                model.typename + "/",
                                model.id)
            log.debug("create %s", url)
            self.s.put(url, data=self.ph.serialize_web(model.to_json()))
        return model
    
    def get(self, typename=None, id=None):
        return self.fetch(typename=typename, id=id)
    
    def fetch(self, typename=None, id=None):
        if typename is None:
            url = utils.urljoin(self.baseurl, self.docid)
            data = self.s.get(url).content
            specs = self.ph.deserialize_web(data)
            models =  [ContinuumModel(
                x['type'], **x['attributes']) for x in specs]
            return models
        elif typename is not None and id is None:
            url = utils.urljoin(self.baseurl, self.docid +"/", typename)
            attrs = self.ph.deserialize_web(self.s.get(url).content)
            models = [ContinuumModel(typename, **x) for x in attrs]
            return models
        elif typename is not None and id is not None:
            url = utils.urljoin(self.baseurl, self.docid +"/", typename + "/", id)
            attr = self.ph.deserialize_web(self.s.get(url).content)
            if attr is None:
                return None
            model = ContinuumModel(typename, **attr)
            return model
        
    def upsert_all(self, models):
        for m in models:
            self.update(m, defer=True)
        self.buffer_sync()
        
