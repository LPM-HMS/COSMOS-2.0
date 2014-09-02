import re
from sqlalchemy.schema import Column, ForeignKey, UniqueConstraint
from sqlalchemy.types import Boolean, Integer, String, DateTime
from sqlalchemy.sql.expression import func
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import relationship, synonym, backref, validates
from sqlalchemy.ext.declarative import declared_attr
from flask import url_for

from ..db import Base
from ..util.sqla import Enum34_ColumnType
from .. import StageStatus, signal_stage_status_change, RelationshipType, TaskStatus
import networkx as nx


@signal_stage_status_change.connect
def task_status_changed(stage):
    stage.log.info('%s %s' % (stage, stage.status))
    if stage.status == StageStatus.successful:
        stage.successful = True

    if stage.status == StageStatus.running:
        stage.started_on = func.now()
    elif stage.status in [StageStatus.successful, StageStatus.failed, StageStatus.killed]:
        stage.finished_on = func.now()

    stage.session.commit()



class Stage(Base):
    __tablename__ = 'stage'
    __table_args__ = (UniqueConstraint('execution_id', 'name', name='_uc_execution_name'),)

    id = Column(Integer, primary_key=True)
    number = Column(Integer)
    name = Column(String(255))
    started_on = Column(DateTime)
    finished_on = Column(DateTime)
    execution_id = Column(ForeignKey('execution.id'),nullable=False)
    execution = relationship("Execution", backref=backref("stages", cascade="all, delete-orphan", order_by="Stage.number"))
    started_on = Column(DateTime)
    finished_on = Column(DateTime)
    relationship_type = Column(Enum34_ColumnType(RelationshipType))
    successful = Column(Boolean, nullable=False, default=False)
    _status = Column(Enum34_ColumnType(StageStatus), default=StageStatus.no_attempt)
    parents = association_proxy('incoming_edges', 'parent', creator=lambda n: StageEdge(parent=n))
    children = association_proxy('outgoing_edges', 'child', creator=lambda n: StageEdge(child=n))


    @declared_attr
    def status(cls):
        def get_status(self):
            return self._status

        def set_status(self, value):
            if self._status != value:
                self._status = value
                signal_stage_status_change.send(self)

        return synonym('_status', descriptor=property(get_status, set_status))

    @validates('name')
    def validate_name(self, key, name):
        assert re.match('^[\w]+$', name), 'Invalid stage name.'
        return name

    def __init__(self, *args, **kwargs):
        super(Stage, self).__init__(*args, **kwargs)

        if not re.match('^[a-zA-Z0-9_\.-]+$', self.name):
            raise Exception('invalid stage name %s' % self.name)

    def num_successful_tasks(self):
        #return self.session.query(Task).filter(Task.stage == self and Task.successful==True).count()
        return len(filter(lambda t: t.successful, self.tasks))

    def num_failed_tasks(self):
        #return self.session.query(Task).filter(Task.stage == self and Task.successful==True).count()
        return len(filter(lambda t: t.status == TaskStatus.failed, self.tasks))

    @property
    def url(self):
        return url_for('cosmos.stage', execution_id=self.execution_id, stage_name=self.name)

    @property
    def log(self):
        return self.execution.log

    def delete(self, delete_files=False):
        self.log.info('Deleting %s' % self)
        if delete_files:
            for t in self.tasks:
                t.delete(delete_files=True)
        self.session.delete(self)
        self.session.commit()

    def get_tasks(self, **filter_by):
        return [t for t in self.tasks if all(str(t.tags.get(k, None)) == v for k, v in filter_by.items())]

    def get_task(self, **filter_by):
        tasks = self.get_tasks(**filter_by)
        assert len(tasks) > 0, 'no task found with tags %s' % filter_by
        assert len(tasks) == 1, 'more than one task with tags %s' % filter_by
        return tasks[0]

    def percent_successful(self):
        return round(float(self.num_successful_tasks()) / (float(len(self.tasks)) or 1) * 100, 2)
    def percent_failed(self):
        return round(float(self.num_failed_tasks()) / (float(len(self.tasks)) or 1) * 100, 2)

    def percent_running(self):
        return round(float(len([t for t in self.tasks if t.status == TaskStatus.submitted])) / (float(len(self.tasks)) or 1) * 100, 2)

    def descendants(self, include_self=False):
        """
        :return: (list) all stages that descend from this stage in the stage_graph
        """
        #return set(it.chain(*breadth_first_search.bfs_successors(self.ex.stage_graph(), self).values()))
        x = nx.descendants(self.execution.stage_graph(), self)
        if include_self:
            return {self}.union(x)
        else:
            return x

    @property
    def label(self):
        return '{0} ({1}/{2})'.format(self.name, self.num_successful_tasks(), len(self.tasks))

    def __repr__(self):
        return '<Stage[%s] %s>' % (self.id or '', self.name)



class StageEdge(Base):
    __tablename__ = 'stage_edge'
    parent_id = Column(Integer, ForeignKey('stage.id'), primary_key=True)
    parent = relationship("Stage", primaryjoin=parent_id == Stage.id, backref=backref("outgoing_edges", cascade="save-update, merge, delete, delete-orphan",single_parent=True))
    child_id = Column(Integer, ForeignKey('stage.id'), primary_key=True)
    child = relationship("Stage",primaryjoin=child_id == Stage.id,  backref=backref("incoming_edges", cascade="save-update, merge, delete, delete-orphan",single_parent=True))

    def __init__(self, parent=None, child=None):
        self.parent = parent
        self.child = child


    def __str__(self):
        return '<StageEdge: %s -> %s>' % (self.parent, self.child)

    def __repr__(self):
        return self.__str__()